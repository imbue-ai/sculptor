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
    and if found, surfaces check status, reviews, and unresolved comments.

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

    # One `gh api graphql` call returns every PR on this source branch (across
    # all states) *with* its check/review/comment detail, so we group by each
    # PR's ``state`` and dispatch locally rather than issuing a second query.
    all_prs = _fetch_prs_with_details(working_dir, current_branch)
    open_prs = [pr for pr in all_prs if pr.get("state") == "OPEN"]
    merged_prs = [pr for pr in all_prs if pr.get("state") == "MERGED"]
    closed_prs = [pr for pr in all_prs if pr.get("state") == "CLOSED"]

    # An open PR against the exact target gets the full status treatment
    # (checks, reviews, comments).
    open_match = _first_matching_target(open_prs, stripped_target)
    if open_match is not None:
        return _build_open_pr_status(workspace_id, open_match)

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

    The query orders PRs most-recently-updated first, so the first match is the
    PR against that target the user most recently touched.
    """
    for pr in prs:
        if pr.get("baseRefName") == target_branch:
            return pr
    return None


def _build_open_pr_status(
    workspace_id: WorkspaceID,
    pr_node: dict,
) -> PrStatusInfo:
    """Build a full PrStatusInfo for an open PR (checks, reviews, comments).

    All detail fields already live on ``pr_node`` (the single graphql query
    fetches them alongside the PR identity), so this does no further I/O.
    """
    return PrStatusInfo(
        workspace_id=workspace_id,
        pr_state="open",
        has_conflicts=_parse_conflict_status(pr_node),
        pr_iid=pr_node["number"],
        pr_title=pr_node.get("title"),
        pr_web_url=pr_node.get("url"),
        pipeline_status=_parse_check_status(pr_node),
        approvals=_parse_reviews(pr_node),
        unresolved_comments=_parse_review_comments(pr_node),
    )


# Upper bound on PRs fetched per source branch in one graphql call. A single
# source branch realistically has only a handful of PRs across its lifetime, so
# one capped fetch (most-recently-updated first) returns every state
# (open/merged/closed) we dispatch on. Each node also pulls check/review detail,
# so this is deliberately small to keep the GraphQL point cost low.
_PR_QUERY_LIMIT = 5

# Single GraphQL query that replaces the old `gh pr list` + `gh pr view` pair.
# It fetches the PR identity *and* its detail in one request, and — unlike
# ``gh pr view --json``'s curated field subset — ``reviewThreads`` is a valid
# field on the GraphQL ``PullRequest`` type, so unresolved-comment surfacing
# actually works. Requesting ``statusCheckRollup { state }`` (one aggregate
# enum) rather than every individual check context also lowers the point cost.
# ``mergeable`` (MERGEABLE / CONFLICTING / UNKNOWN) surfaces merge conflicts so
# the CI babysitter can act on a conflicted PR the same way it does for an MR.
# ``{owner}`` / ``{repo}`` in the field args are expanded by gh from the
# working directory's ``origin`` remote, so no repo plumbing is needed here.
_GRAPHQL_PR_QUERY = """
query($owner: String!, $name: String!, $branch: String!, $limit: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequests(headRefName: $branch, first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number
        title
        url
        state
        baseRefName
        mergeable
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
        latestReviews(first: 20) { nodes { state author { login } } }
        reviewThreads(first: 30) {
          nodes { isResolved comments(first: 1) { nodes { author { login } path line body } } }
        }
      }
    }
  }
}
"""


def _fetch_prs_with_details(working_dir: Path, source_branch: str) -> list[dict]:
    """Fetch all PRs (open/merged/closed) for a source branch, with detail.

    Issues a single ``gh api graphql`` request. Each returned node carries its
    ``state`` (``OPEN`` / ``MERGED`` / ``CLOSED``) for local dispatch, its base
    branch (so a PR opened against a *different* target can be detected for the
    "switch target" affordance), and the check/review/comment detail used to
    build an open PR's full status. Returns up to ``_PR_QUERY_LIMIT`` PRs,
    most-recently-updated first, or an empty list if the repository can't be
    resolved.

    Raises CliStatusError on any CLI failure (including rate limits, classified
    via ``classify_cli_error``) so the poller can surface it and back off.
    """
    cmd = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={_GRAPHQL_PR_QUERY}",
        "-F",
        "owner={owner}",
        "-F",
        "name={repo}",
        "-f",
        f"branch={source_branch}",
        "-F",
        f"limit={_PR_QUERY_LIMIT}",
    ]
    result = run_cli_with_retry(cmd, working_dir)
    if result.returncode != 0:
        raise CliStatusError(classify_cli_error(result.stderr), result.stderr)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CliStatusError("transient", f"Invalid JSON from gh api graphql: {result.stdout[:200]}") from e
    repository = (payload.get("data") or {}).get("repository")
    if repository is None:
        return []
    return (repository.get("pullRequests") or {}).get("nodes") or []


def _parse_conflict_status(pr_node: dict) -> bool | None:
    """Map a PR's GitHub ``mergeable`` enum to our tri-state conflict flag.

    GitHub computes mergeability asynchronously and exposes it as
    ``MERGEABLE`` / ``CONFLICTING`` / ``UNKNOWN``. ``CONFLICTING`` means the PR
    cannot merge cleanly into its base (a merge conflict); ``MERGEABLE`` means
    it can. ``UNKNOWN`` (GitHub hasn't finished computing, common right after a
    push) and any unrecognized/missing value map to None, so we neither claim a
    conflict nor claim cleanliness until GitHub is sure. The resulting tri-state
    ``has_conflicts`` (bool | None) drives the CI babysitter's MERGE_CONFLICT
    transition.
    """
    mergeable = pr_node.get("mergeable")
    if mergeable == "CONFLICTING":
        return True
    if mergeable == "MERGEABLE":
        return False
    return None


def _parse_check_status(pr_node: dict) -> Literal["running", "passed", "failed"] | None:
    """Map a PR's aggregate status-check rollup to our three-state model.

    Reads ``statusCheckRollup.state`` from the PR's most recent commit. GitHub
    already collapses every check context into one ``StatusState`` enum, so we
    map that single value instead of scanning individual checks. Returns None
    when the commit has no checks (the rollup is null) or reports a state we
    don't recognize.
    """
    commit_nodes = (pr_node.get("commits") or {}).get("nodes") or []
    if not commit_nodes:
        return None
    rollup = (commit_nodes[0].get("commit") or {}).get("statusCheckRollup")
    if rollup is None:
        return None
    state = rollup.get("state", "")
    if state in ("FAILURE", "ERROR"):
        return "failed"
    if state in ("PENDING", "EXPECTED"):
        return "running"
    if state == "SUCCESS":
        return "passed"
    return None


def _parse_reviews(pr_node: dict) -> list[PrApproval]:
    """Extract approve / request-changes reviews from a PR's latest reviews.

    ``latestReviews`` already returns the most recent review per reviewer, so
    no per-author de-duplication is needed.
    """
    review_nodes = (pr_node.get("latestReviews") or {}).get("nodes") or []
    approvals: list[PrApproval] = []
    for review in review_nodes:
        state = review.get("state", "")
        if state not in ("APPROVED", "CHANGES_REQUESTED"):
            continue
        author = (review.get("author") or {}).get("login", "unknown")
        approvals.append(PrApproval(name=author, approved=state == "APPROVED"))
    return approvals


def _parse_review_comments(pr_node: dict) -> list[PrComment]:
    thread_nodes = (pr_node.get("reviewThreads") or {}).get("nodes") or []
    comments: list[PrComment] = []
    for thread in thread_nodes:
        if thread.get("isResolved"):
            continue
        comment_nodes = (thread.get("comments") or {}).get("nodes") or []
        if not comment_nodes:
            continue
        first_comment = comment_nodes[0]
        comments.append(
            PrComment(
                author=(first_comment.get("author") or {}).get("login", "unknown"),
                file_path=first_comment.get("path", ""),
                line=first_comment.get("line"),
                body=first_comment.get("body", ""),
            )
        )
    return comments
