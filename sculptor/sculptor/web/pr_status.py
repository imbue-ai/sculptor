import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from loguru import logger

from sculptor.primitives.ids import WorkspaceID
from sculptor.web.cli_status_utils import CliStatusError
from sculptor.web.cli_status_utils import classify_cli_error
from sculptor.web.cli_status_utils import run_cli_with_retry
from sculptor.web.cli_status_utils import strip_remote_prefix
from sculptor.web.derived import PrApproval
from sculptor.web.derived import PrComment
from sculptor.web.derived import PrStatusInfo


def fetch_pr_status(
    workspace_id: WorkspaceID,
    working_dir: Path,
    current_branch: str,
    target_branch: str,
) -> PrStatusInfo:
    """Fetch PR status from GitHub for a workspace's current and target branch.

    Calls the gh CLI to find an open or merged PR matching the branches,
    and if found, fetches check status, reviews, and unresolved comments.

    If no open PR matches the exact source+target pair but an open PR exists
    on the source branch targeting a different branch, the mismatch fields
    are populated so the frontend can warn the user.

    Returns a PrStatusInfo with error_category set if the CLI is missing
    or returns a classifiable error. The caller is responsible for
    verifying the origin is GitHub before calling this function.
    """
    try:
        return _fetch_pr_status_inner(workspace_id, working_dir, current_branch, target_branch)
    except CliStatusError as e:
        logger.debug("PR status check failed ({}): {}", e.category, e)
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="none",
            error_category=e.category,
            error_provider="github",
            error_message=str(e),
        )


def _fetch_pr_status_inner(
    workspace_id: WorkspaceID,
    working_dir: Path,
    current_branch: str,
    target_branch: str,
) -> PrStatusInfo:
    """Inner implementation that raises CliStatusError on CLI failures."""
    stripped_target = strip_remote_prefix(target_branch)

    # One `gh pr list` call returns every PR on this source branch regardless
    # of state; we group by each PR's ``state`` and dispatch locally rather
    # than issuing a separate query per state.
    all_prs = _find_all_prs(working_dir, current_branch)
    open_prs = [pr for pr in all_prs if pr.get("state") == "OPEN"]
    merged_prs = [pr for pr in all_prs if pr.get("state") == "MERGED"]
    closed_prs = [pr for pr in all_prs if pr.get("state") == "CLOSED"]

    # An open PR against the exact target gets the full status treatment
    # (checks, reviews, comments).
    open_match = _first_matching_target(open_prs, stripped_target)
    if open_match is not None:
        return _build_open_pr_status(workspace_id, working_dir, open_match)

    # Otherwise prefer a terminal state for the exact target. Merged wins over
    # closed: GitHub PR states are disjoint (a merged PR is MERGED, never
    # CLOSED), so a target with both a merged and a closed PR in its history
    # has genuinely landed.
    merged_match = _first_matching_target(merged_prs, stripped_target)
    if merged_match is not None:
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="merged",
            pr_iid=merged_match["number"],
            pr_title=merged_match.get("title"),
            pr_web_url=merged_match.get("url"),
        )

    closed_match = _first_matching_target(closed_prs, stripped_target)
    if closed_match is not None:
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="closed",
            pr_iid=closed_match["number"],
            pr_title=closed_match.get("title"),
            pr_web_url=closed_match.get("url"),
        )

    # No PR targets this branch — if an open PR exists against a different
    # target, surface it so the frontend can offer to switch targets.
    if open_prs:
        mismatched_pr = open_prs[0]
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="none",
            mismatched_pr_iid=mismatched_pr["number"],
            mismatched_pr_target_branch=mismatched_pr.get("baseRefName"),
            mismatched_pr_web_url=mismatched_pr.get("url"),
        )

    return PrStatusInfo(workspace_id=workspace_id, pr_state="none")


def _first_matching_target(prs: Sequence[dict], target_branch: str) -> dict | None:
    """Return the first PR whose base branch equals ``target_branch``, if any.

    ``gh pr list`` returns PRs newest-first, so the first match is the most
    recently created PR against that target.
    """
    for pr in prs:
        if pr.get("baseRefName") == target_branch:
            return pr
    return None


def _build_open_pr_status(
    workspace_id: WorkspaceID,
    working_dir: Path,
    pr_data: dict,
) -> PrStatusInfo:
    """Build a full PrStatusInfo for an open PR (checks, reviews, comments)."""
    pr_number = pr_data["number"]
    details = _fetch_pr_details(working_dir, pr_number)

    return PrStatusInfo(
        workspace_id=workspace_id,
        pr_state="open",
        pr_iid=pr_number,
        pr_title=pr_data.get("title"),
        pr_web_url=pr_data.get("url"),
        pipeline_status=_parse_check_status(details),
        approvals=_parse_reviews(details),
        unresolved_comments=_parse_review_comments(details),
    )


# Upper bound on PRs fetched per source branch in one `gh pr list` call. A
# single source branch realistically has only a handful of PRs across its
# lifetime, so one capped fetch returns every state (open/merged/closed) we
# dispatch on without needing a per-state round trip.
_PR_LIST_LIMIT = 30


def _find_all_prs(working_dir: Path, source_branch: str) -> list[dict]:
    """Find all PRs (open, merged, or closed) for a source branch.

    ``--state=all`` returns PRs in every state; each row carries a ``state``
    field (``OPEN`` / ``MERGED`` / ``CLOSED``) that the caller dispatches on.
    No ``--base`` filter is applied, so the caller can also detect a PR opened
    against a *different* target branch (the "switch target" affordance).
    Returns up to ``_PR_LIST_LIMIT`` PRs, newest first.
    """
    cmd = [
        "gh",
        "pr",
        "list",
        f"--head={source_branch}",
        "--state=all",
        "--json",
        "number,title,url,baseRefName,state",
        "--limit",
        str(_PR_LIST_LIMIT),
    ]
    result = run_cli_with_retry(cmd, working_dir)
    if result.returncode != 0:
        raise CliStatusError(classify_cli_error(result.stderr), result.stderr)
    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CliStatusError("transient", f"Invalid JSON from gh pr list: {result.stdout[:200]}") from e
    return prs


def _fetch_pr_details(working_dir: Path, pr_number: int) -> dict:
    """Fetch checks, reviews, and review threads for an open PR in one call.

    ``gh pr view`` issues a single GraphQL request no matter how many
    ``--json`` fields are requested, so bundling ``statusCheckRollup``,
    ``reviews``, and ``reviewThreads`` into one invocation collapses what
    used to be three separate GraphQL round trips into one. That detail
    fetch is the dominant per-poll cost for a workspace with an open PR, so
    this roughly halves the GraphQL points spent polling it.

    On a non-rate-limit failure this returns an empty dict so the caller
    still reports the open PR (just without check/review detail), matching
    the previous best-effort behaviour. A rate-limit failure is re-raised as
    ``CliStatusError`` so the poller can surface it and back off instead of
    silently dropping the signal.
    """
    result = run_cli_with_retry(
        ["gh", "pr", "view", str(pr_number), "--json", "statusCheckRollup,reviews,reviewThreads"],
        working_dir,
    )
    if result.returncode != 0:
        category = classify_cli_error(result.stderr)
        if category == "rate_limited":
            raise CliStatusError(category, result.stderr)
        logger.debug("gh pr view details failed ({}): {}", category, result.stderr)
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.debug("Invalid JSON from gh pr view details: {}", result.stdout[:200])
        return {}


def _parse_check_status(details: dict) -> Literal["running", "passed", "failed"] | None:
    checks = details.get("statusCheckRollup", [])
    if not checks:
        return None

    has_running = False
    has_failed = False
    for check in checks:
        conclusion = check.get("conclusion", "")
        status = check.get("status", "")
        if status in ("IN_PROGRESS", "QUEUED", "PENDING", "WAITING") or conclusion == "":
            has_running = True
        elif conclusion in ("FAILURE", "CANCELLED", "TIMED_OUT", "ERROR"):
            has_failed = True

    if has_failed:
        return "failed"
    if has_running:
        return "running"
    return "passed"


def _parse_reviews(details: dict) -> list[PrApproval]:
    reviews = details.get("reviews", [])
    # Keep only the latest review per author
    latest_by_author: dict[str, PrApproval] = {}
    for review in reviews:
        state = review.get("state", "")
        if state not in ("APPROVED", "CHANGES_REQUESTED"):
            continue
        author = review.get("author", {}).get("login", "unknown")
        latest_by_author[author] = PrApproval(name=author, approved=state == "APPROVED")
    return list(latest_by_author.values())


def _parse_review_comments(details: dict) -> list[PrComment]:
    threads = details.get("reviewThreads", [])
    comments: list[PrComment] = []
    for thread in threads:
        if thread.get("isResolved"):
            continue
        thread_comments = thread.get("comments", [])
        if not thread_comments:
            continue
        first_comment = thread_comments[0]
        comments.append(
            PrComment(
                author=first_comment.get("author", {}).get("login", "unknown"),
                file_path=first_comment.get("path", ""),
                line=first_comment.get("line"),
                body=first_comment.get("body", ""),
            )
        )
    return comments
