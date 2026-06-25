import json
from collections.abc import Sequence
from dataclasses import dataclass
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
# the CI babysitter can act on a conflicted PR.
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
        reviewThreads(first: 10) {
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


# Page size for the token-wide search query. One page covers every open PR for
# a user with up to this many open PRs (the overwhelmingly common case); the
# fetch only paginates beyond it (and logs when it does).
_SEARCH_PAGE_SIZE = 100

# The GitHub search filter. ``author:@me`` scopes the search to the token
# owner's own PRs (every PR a Sculptor workspace opens is authored by the token
# owner), so a single token-global query spans every repo with no repo
# enumeration. ``sort:updated`` is required, not cosmetic: ``_first_matching_target``
# returns the *first* PR matching a base branch and relies on most-recently-updated
# ordering, but ``search`` otherwise defaults to relevance order.
_SEARCH_QUERY_STRING = "is:pr state:open author:@me archived:false sort:updated"

# Token-wide search query that replaces one ``_GRAPHQL_PR_QUERY`` per workspace
# with one query per (host, token) per round. ``author:@me`` returns all of the
# user's open PRs across every repo at once, each node carrying the same
# check/review/comment/``mergeable`` detail the per-workspace query does, plus
# ``repository { nameWithOwner }`` and ``headRefName`` so the poller can index a
# node back to the workspace(s) it belongs to. The sibling ``rateLimit`` block
# rides in the same response so the governor can read the token's budget with no
# extra call. ``reviewThreads`` is trimmed to 10 and ``latestReviews`` left at 20
# (cost-free — it nests no connection).
_SEARCH_PR_QUERY = """
query($q: String!, $prCount: Int!, $after: String) {
  search(query: $q, type: ISSUE, first: $prCount, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        url
        state
        baseRefName
        repository { nameWithOwner }
        headRefName
        mergeable
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
        latestReviews(first: 20) { nodes { state author { login } } }
        reviewThreads(first: 10) {
          nodes { isResolved comments(first: 1) { nodes { author { login } path line body } } }
        }
      }
    }
  }
  rateLimit { cost remaining limit resetAt }
}
"""


@dataclass(frozen=True)
class GithubRateLimit:
    """GitHub API rate-budget snapshot parsed from a query's ``rateLimit`` block.

    ``cost`` is the points the query consumed; ``remaining`` / ``limit`` and the
    ISO-8601 ``reset_at`` describe the token's hourly budget. Consumed by the
    rate-budget governor to back off proactively before the wall.
    """

    cost: int
    remaining: int
    limit: int
    reset_at: str


@dataclass(frozen=True)
class OpenPrSearchResult:
    """All of a token owner's open-PR nodes plus the round's rate-budget snapshot.

    ``nodes`` are raw ``... on PullRequest`` dicts (open state only — terminal
    PRs are not in a ``state:open`` search); ``rate_limit`` is the response's
    ``rateLimit`` block, or ``None`` when it is absent from a malformed response.
    """

    nodes: list[dict]
    rate_limit: GithubRateLimit | None


def fetch_open_prs_for_token(working_dir: Path) -> OpenPrSearchResult:
    """Fetch every open PR authored by the token owner in one search query.

    Issues a single ``gh api graphql`` ``search`` request (``author:@me``,
    token-global — not repo-scoped) returning all of the user's open PRs across
    every repo, each with the per-PR check/review/comment detail the
    per-workspace query carries. Paginates only when the user has more than
    ``_SEARCH_PAGE_SIZE`` open PRs (rare), logging a warning when it does so
    silent truncation can't masquerade as full coverage. Returns the
    accumulated nodes plus the token's ``rateLimit`` snapshot (``None`` if the
    block is absent) for the governor.

    Raises CliStatusError on any CLI failure (classified via
    ``classify_cli_error``) or invalid JSON, so the poller can surface it and
    back off.
    """
    nodes: list[dict] = []
    rate_limit: GithubRateLimit | None = None
    after: str | None = None
    page = 1
    while True:
        payload = _run_search_query(working_dir, after)
        search = (payload.get("data") or {}).get("search") or {}
        nodes.extend(search.get("nodes") or [])
        rate_limit = _parse_rate_limit(payload)
        page_info = search.get("pageInfo") or {}
        if not (page_info.get("hasNextPage") and page_info.get("endCursor")):
            break
        after = page_info["endCursor"]
        page += 1
        logger.warning(
            "PR search returned more than {} open PRs; following pagination to page {}",
            _SEARCH_PAGE_SIZE,
            page,
        )
    return OpenPrSearchResult(nodes=nodes, rate_limit=rate_limit)


def _run_search_query(working_dir: Path, after: str | None) -> dict:
    """Run one page of the token-wide search query and return its parsed payload.

    Unlike ``_fetch_prs_with_details`` there is no ``owner``/``name`` arg —
    search is token-global, not repo-scoped — but ``gh`` still needs a directory
    to resolve the token/host. Raises CliStatusError on CLI failure or invalid
    JSON, mirroring ``_fetch_prs_with_details``.
    """
    cmd = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={_SEARCH_PR_QUERY}",
        "-f",
        f"q={_SEARCH_QUERY_STRING}",
        "-F",
        f"prCount={_SEARCH_PAGE_SIZE}",
    ]
    if after is not None:
        cmd += ["-f", f"after={after}"]
    result = run_cli_with_retry(cmd, working_dir)
    if result.returncode != 0:
        raise CliStatusError(classify_cli_error(result.stderr), result.stderr)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CliStatusError("transient", f"Invalid JSON from gh api graphql: {result.stdout[:200]}") from e


def _parse_rate_limit(payload: dict) -> GithubRateLimit | None:
    """Parse a response's ``rateLimit`` block, or ``None`` if it is absent.

    Kept tolerant of a missing or partial block so a malformed response degrades
    (governor falls back to its default budget) instead of crashing the round.
    """
    block = (payload.get("data") or {}).get("rateLimit")
    if not isinstance(block, dict):
        return None
    cost = block.get("cost")
    remaining = block.get("remaining")
    limit = block.get("limit")
    reset_at = block.get("resetAt")
    if cost is None or remaining is None or limit is None or reset_at is None:
        return None
    return GithubRateLimit(cost=cost, remaining=remaining, limit=limit, reset_at=reset_at)


def build_status_from_open_nodes(
    workspace_id: WorkspaceID,
    open_nodes: Sequence[dict],
    target_branch: str,
) -> PrStatusInfo:
    """Derive one workspace's open-PR status from the token-wide search nodes.

    Pure (no I/O): given the open-PR nodes already filtered to this workspace's
    ``(repo, head branch)``, pick the PR whose base matches its target and reuse
    the per-node parsers. Handles only the open and no-open-PR cases — terminal
    (merged/closed) PRs are absent from a ``state:open`` search and are recovered
    by the per-workspace fallback. Mirrors ``_fetch_pr_status_inner``'s open and
    mismatch branches so behavior matches today for the open case.
    """
    stripped_target = strip_remote_prefix(target_branch)
    open_match = _first_matching_target(open_nodes, stripped_target)
    if open_match is not None:
        return _build_open_pr_status(workspace_id, open_match)
    # No open PR targets this branch — if one exists against a different target,
    # surface it so the frontend can offer to switch targets.
    if open_nodes:
        mismatched_pr = open_nodes[0]
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="none",
            mismatched_pr_iid=mismatched_pr["number"],
            mismatched_pr_target_branch=mismatched_pr.get("baseRefName"),
            mismatched_pr_web_url=mismatched_pr.get("url"),
        )
    return PrStatusInfo(workspace_id=workspace_id, pr_state="none")


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
