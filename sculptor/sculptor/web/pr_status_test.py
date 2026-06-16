import json
import os
import re
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.cli_status_utils import CliStatusError
from sculptor.web.pr_status import _GRAPHQL_PR_QUERY
from sculptor.web.pr_status import _PR_QUERY_LIMIT
from sculptor.web.pr_status import _SEARCH_PAGE_SIZE
from sculptor.web.pr_status import _SEARCH_PR_QUERY
from sculptor.web.pr_status import _SEARCH_QUERY_STRING
from sculptor.web.pr_status import build_status_from_open_nodes
from sculptor.web.pr_status import fetch_open_prs_for_token
from sculptor.web.pr_status import fetch_pr_status


def _make_finished(stdout: str, returncode: int = 0, stderr: str = "") -> FinishedProcess:
    return FinishedProcess(
        stdout=stdout, stderr=stderr, returncode=returncode, command=("gh",), is_output_already_logged=False
    )


WORKSPACE_ID = WorkspaceID()
WORKING_DIR = Path("/tmp/repo")


def _pr_node(
    number: int,
    state: str,
    base_ref: str = "main",
    check_state: str | None = None,
    reviews: list[dict] | None = None,
    threads: list[dict] | None = None,
    mergeable: str | None = None,
    is_in_merge_queue: bool = False,
) -> dict:
    """Build one graphql ``pullRequests.nodes`` entry in the given GitHub state.

    Mirrors the shape returned by the single ``gh api graphql`` query the
    backend now issues: identity fields alongside the check/review/comment
    detail (``statusCheckRollup`` is null when no checks have run). ``mergeable``
    is GitHub's ``MERGEABLE`` / ``CONFLICTING`` / ``UNKNOWN`` merge-conflict enum;
    it is included only when provided so unrelated tests keep their minimal shape.
    ``isInMergeQueue`` reports merge-queue membership and is always present, just
    as the live query returns it.
    """
    rollup = {"state": check_state} if check_state is not None else None
    node = {
        "number": number,
        "title": f"PR #{number}",
        "url": f"https://github.com/org/repo/pull/{number}",
        "state": state,
        "baseRefName": base_ref,
        "isInMergeQueue": is_in_merge_queue,
        "commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]},
        "latestReviews": {"nodes": reviews or []},
        "reviewThreads": {"nodes": threads or []},
    }
    if mergeable is not None:
        node["mergeable"] = mergeable
    return node


def _open_node(number: int, base_ref: str = "main", **kwargs) -> dict:  # noqa: ANN003
    return _pr_node(number, "OPEN", base_ref, **kwargs)


def _merged_node(number: int, base_ref: str = "main") -> dict:
    return _pr_node(number, "MERGED", base_ref)


def _closed_node(number: int, base_ref: str = "main") -> dict:
    return _pr_node(number, "CLOSED", base_ref)


def _graphql_stdout(nodes: list[dict]) -> str:
    """Wrap PR nodes in the graphql response envelope gh emits."""
    return json.dumps({"data": {"repository": {"pullRequests": {"nodes": nodes}}}})


def _patch_cli(side_effect):  # noqa: ANN001
    return patch("sculptor.web.pr_status.run_cli_with_retry", side_effect=side_effect)


def _graphql_handler(nodes: list[dict]):  # noqa: ANN001
    """Build a cli_handler for the single `gh api graphql` call.

    The backend issues exactly one graphql request that returns every PR on the
    source branch (across all states) with its check/review/comment detail
    bundled in. This handler returns ``nodes`` wrapped in the graphql envelope.
    """

    def handler(cmd, _working_dir):  # noqa: ANN001
        if "graphql" in cmd:
            return _make_finished(_graphql_stdout(nodes))
        return _make_finished("[]")

    return handler


def _captured_query(cmd: list[str]) -> str:
    """Return the GraphQL query string passed as `-f query=...` in a gh command."""
    for arg in cmd:
        if arg.startswith("query="):
            return arg[len("query=") :]
    raise AssertionError(f"no query= argument found in command: {cmd}")


def test_open_pr_matching_target() -> None:
    with _patch_cli(_graphql_handler([_open_node(100, base_ref="main")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 100
    assert result.mismatched_pr_iid is None


def test_open_pr_mismatched_target() -> None:
    with _patch_cli(_graphql_handler([_open_node(200, base_ref="develop")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid == 200
    assert result.mismatched_pr_target_branch == "develop"
    assert result.mismatched_pr_web_url == "https://github.com/org/repo/pull/200"


def test_no_prs_at_all() -> None:
    with _patch_cli(_graphql_handler([])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid is None


def test_merged_pr_matching_target() -> None:
    with _patch_cli(_graphql_handler([_merged_node(300, base_ref="main")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "merged"
    assert result.pr_iid == 300
    assert result.mismatched_pr_iid is None


def test_multiple_open_prs_one_matches() -> None:
    nodes = [
        _open_node(400, base_ref="develop"),
        _open_node(401, base_ref="main"),
    ]

    with _patch_cli(_graphql_handler(nodes)):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 401
    assert result.mismatched_pr_iid is None


def test_multiple_open_prs_none_match() -> None:
    nodes = [
        _open_node(500, base_ref="develop"),
        _open_node(501, base_ref="staging"),
    ]

    with _patch_cli(_graphql_handler(nodes)):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid == 500
    assert result.mismatched_pr_target_branch == "develop"


def test_closed_pr_matching_target() -> None:
    with _patch_cli(_graphql_handler([_closed_node(800, base_ref="main")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "closed"
    assert result.pr_iid == 800
    assert result.pr_title == "PR #800"
    assert result.pr_web_url == "https://github.com/org/repo/pull/800"


def test_merged_takes_precedence_over_closed() -> None:
    # A branch whose first PR was closed and whose second PR landed: the single
    # query returns both, and local dispatch must prefer merged.
    nodes = [
        _merged_node(820, base_ref="main"),
        _closed_node(810, base_ref="main"),
    ]

    with _patch_cli(_graphql_handler(nodes)):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "merged"
    assert result.pr_iid == 820


def test_open_pr_details_fetched_in_single_graphql_call() -> None:
    calls: list[list] = []

    node = _open_node(
        42,
        check_state="SUCCESS",
        reviews=[{"state": "APPROVED", "author": {"login": "alice"}}],
        threads=[
            {
                "isResolved": False,
                "comments": {"nodes": [{"author": {"login": "bob"}, "path": "a.py", "line": 3, "body": "fix"}]},
            }
        ],
    )

    def handler(cmd, _working_dir):  # noqa: ANN001
        calls.append(cmd)
        return _make_finished(_graphql_stdout([node]))

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pipeline_status == "passed"
    assert [a.name for a in result.approvals] == ["alice"]
    assert len(result.unresolved_comments) == 1
    assert result.unresolved_comments[0].author == "bob"
    assert result.is_in_merge_queue is False
    # Exactly one CLI call, and it is a `gh api graphql` request (not the old
    # `gh pr list` + `gh pr view` pair).
    assert len(calls) == 1
    assert calls[0][:3] == ["gh", "api", "graphql"]


# ---------------------------------------------------------------------------
# Open PR sitting in the merge queue → is_in_merge_queue=True.
# ---------------------------------------------------------------------------


def test_open_pr_in_merge_queue() -> None:
    with _patch_cli(_graphql_handler([_open_node(55, is_in_merge_queue=True)])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 55
    assert result.is_in_merge_queue is True


# ---------------------------------------------------------------------------
# Regression for the shipped bug: a failing check must reach pipeline_status.
# An invalid `gh pr view --json` field used to poison the whole detail fetch,
# so a failing CI never surfaced. The graphql rollup state must now map through.
# ---------------------------------------------------------------------------


def test_failed_check_rollup_surfaces_as_failed_pipeline() -> None:
    node = _open_node(59, check_state="FAILURE")
    with _patch_cli(_graphql_handler([node])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 59
    assert result.pipeline_status == "failed"


@pytest.mark.parametrize(
    ("rollup_state", "expected"),
    [
        ("FAILURE", "failed"),
        ("ERROR", "failed"),
        ("PENDING", "running"),
        ("EXPECTED", "running"),
        ("SUCCESS", "passed"),
        (None, None),
        ("SOMETHING_NEW", None),
    ],
)
def test_status_check_rollup_state_maps_to_pipeline_status(rollup_state: str | None, expected: str | None) -> None:
    node = _open_node(10, check_state=rollup_state)
    with _patch_cli(_graphql_handler([node])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pipeline_status == expected


# ---------------------------------------------------------------------------
# Open PR merge conflict → has_conflicts flows through.
# GitHub reports mergeability via the ``mergeable`` enum; CONFLICTING means the
# PR cannot merge cleanly. Surfacing it as has_conflicts=True is what lets the
# CI babysitter's MERGE_CONFLICT transition fire for PRs.
# ---------------------------------------------------------------------------


def test_open_pr_has_conflicts_flag_flows_through() -> None:
    with _patch_cli(_graphql_handler([_open_node(700, mergeable="CONFLICTING")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.has_conflicts is True


@pytest.mark.parametrize(
    ("mergeable", "expected"),
    [
        ("CONFLICTING", True),
        ("MERGEABLE", False),
        # GitHub computes mergeability asynchronously; UNKNOWN (common right
        # after a push) and any unrecognized/absent value stay None so we never
        # claim a conflict — or claim cleanliness — before GitHub is sure.
        ("UNKNOWN", None),
        (None, None),
        ("SOMETHING_NEW", None),
    ],
)
def test_mergeable_state_maps_to_has_conflicts(mergeable: str | None, expected: bool | None) -> None:
    with _patch_cli(_graphql_handler([_open_node(10, mergeable=mergeable)])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.has_conflicts is expected


# ---------------------------------------------------------------------------
# The query must request the fields the parser reads, via `gh api graphql`.
# This is the unit-level guard against regressing to the broken approach
# (mocks can never exercise real gh field validation — see the live test below).
# ---------------------------------------------------------------------------


def test_graphql_query_requests_the_fields_the_parser_reads() -> None:
    captured: list[list] = []

    def handler(cmd, _working_dir):  # noqa: ANN001
        captured.append(cmd)
        return _make_finished(_graphql_stdout([]))

    with _patch_cli(handler):
        fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[:3] == ["gh", "api", "graphql"]
    query = _captured_query(cmd)
    # Every field the parser navigates must be present in the query.
    for field in (
        "statusCheckRollup",
        "state",
        "baseRefName",
        "latestReviews",
        "reviewThreads",
        "commits",
        "mergeable",
        "isInMergeQueue",
    ):
        assert field in query, f"query is missing field {field!r}"
    # `reviewThreads` is requested directly (it is a valid GraphQL PullRequest
    # field, unlike `gh pr view --json`'s curated subset that shipped the bug).
    # Its page size is trimmed to 10 (Change-1b) — `reviewThreads` is the
    # dominant cost term, so this caps the per-poll GraphQL point cost.
    assert "reviewThreads(first: 10)" in query


# ---------------------------------------------------------------------------
# A non-rate-limit CLI failure is surfaced as its classified category.
# (With a single combined call there is no partial result to degrade to.)
# ---------------------------------------------------------------------------


def test_transient_cli_failure_surfaces_error() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished("", returncode=1, stderr="HTTP 500 Internal Server Error")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.error_category == "transient"


# ---------------------------------------------------------------------------
# An unknown-field / usage error is NOT misclassified as not_authenticated.
# gh's help text lists "author", which used to match the loose 'auth' check.
# ---------------------------------------------------------------------------


def test_unknown_field_usage_error_not_classified_as_not_authenticated() -> None:
    stderr = 'Unknown JSON field: "reviewThreads"\nAvailable fields:\n  author\n  authorAssociation\n  state\n'

    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished("", returncode=1, stderr=stderr)

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.error_category != "not_authenticated"
    assert result.error_category == "transient"


def test_rate_limit_surfaces_error() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished("", returncode=1, stderr="HTTP 403: API rate limit exceeded for user")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.error_category == "rate_limited"


def test_secondary_rate_limit_surfaces_error() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished("", returncode=1, stderr="You have exceeded a secondary rate limit.")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.error_category == "rate_limited"


# ---------------------------------------------------------------------------
# Malformed / missing repository data degrades to no-PR rather than crashing.
# ---------------------------------------------------------------------------


def test_null_repository_in_payload_returns_none() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished(json.dumps({"data": {"repository": None}}))

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.error_category is None


# ---------------------------------------------------------------------------
# Opt-in: validate the real query against GitHub's live GraphQL schema.
#
# Mocked tests cannot catch an invalid field name — that is exactly how the
# `reviewThreads` bug shipped. Set SCULPTOR_PR_STATUS_LIVE_GH_TEST=1 (with an
# authenticated `gh`) to run the actual query so an unrecognized field fails
# loudly with a non-zero exit.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("SCULPTOR_PR_STATUS_LIVE_GH_TEST"),
    reason="opt-in: set SCULPTOR_PR_STATUS_LIVE_GH_TEST=1 to validate against real GitHub",
)
def test_graphql_query_is_valid_against_live_github() -> None:
    if shutil.which("gh") is None:
        pytest.skip("gh CLI not available")
    result = run_blocking(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={_GRAPHQL_PR_QUERY}",
            "-F",
            "owner=imbue-ai",
            "-F",
            "name=sculptor",
            "-f",
            "branch=main",
            "-F",
            f"limit={_PR_QUERY_LIMIT}",
        ],
        timeout=30.0,
        is_checked=False,
        cwd=Path(__file__).parent,
    )
    assert result.returncode == 0, f"gh api graphql rejected the query: {result.stderr}"
    payload = json.loads(result.stdout)
    nodes = payload["data"]["repository"]["pullRequests"]["nodes"]
    assert isinstance(nodes, list)


# ---------------------------------------------------------------------------
# Token-wide `search` fetch + per-workspace derivation (Change-1 building blocks).
# ---------------------------------------------------------------------------


_DEFAULT_RATE_LIMIT = {"cost": 1, "remaining": 4999, "limit": 5000, "resetAt": "2026-01-01T00:00:00Z"}


def _search_node(
    number: int,
    base_ref: str = "main",
    head_ref: str = "feat-1",
    repo: str = "org/repo",
    **kwargs,  # noqa: ANN003
) -> dict:
    """Build one search ``... on PullRequest`` node (always OPEN — search is state:open).

    Extends the per-workspace ``_pr_node`` shape with the two fields only the
    search query carries: ``repository.nameWithOwner`` and ``headRefName``.
    """
    node = _pr_node(number, "OPEN", base_ref, **kwargs)
    node["repository"] = {"nameWithOwner": repo}
    node["headRefName"] = head_ref
    return node


def _search_stdout(
    nodes: list[dict],
    *,
    has_next: bool = False,
    end_cursor: str | None = None,
    rate_limit: dict | None = _DEFAULT_RATE_LIMIT,
) -> str:
    """Wrap search nodes in the envelope gh emits for the token-wide search query."""
    return json.dumps(
        {
            "data": {
                "search": {
                    "nodes": nodes,
                    "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                },
                "rateLimit": rate_limit,
            }
        }
    )


def _captured_search_string(cmd: list[str]) -> str:
    """Return the `-f q=...` search filter passed in a gh command (not `query=`)."""
    for arg in cmd:
        if arg.startswith("q="):
            return arg[len("q=") :]
    raise AssertionError(f"no q= argument found in command: {cmd}")


def test_fetch_open_prs_for_token_single_page() -> None:
    captured: list[list] = []

    def handler(cmd, _working_dir):  # noqa: ANN001
        captured.append(cmd)
        return _make_finished(_search_stdout([_search_node(100), _search_node(101)]))

    with _patch_cli(handler):
        result = fetch_open_prs_for_token(WORKING_DIR)

    assert [n["number"] for n in result.nodes] == [100, 101]
    assert result.rate_limit is not None
    assert result.rate_limit.cost == 1
    assert result.rate_limit.remaining == 4999
    assert result.rate_limit.limit == 5000
    assert result.rate_limit.reset_at == "2026-01-01T00:00:00Z"

    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[:3] == ["gh", "api", "graphql"]
    # The search is token-global, not repo-scoped — no owner/name args.
    assert not any(arg.startswith("owner=") or arg.startswith("name=") for arg in cmd)
    search_string = _captured_search_string(cmd)
    assert "author:@me" in search_string
    assert "state:open" in search_string
    assert "sort:updated" in search_string
    query = _captured_query(cmd)
    for field in (
        "mergeable",
        "isInMergeQueue",
        "nameWithOwner",
        "headRefName",
        "reviewThreads(first: 10)",
        "rateLimit",
    ):
        assert field in query, f"search query is missing {field!r}"


def test_fetch_open_prs_for_token_paginates() -> None:
    captured: list[list] = []

    def handler(cmd, _working_dir):  # noqa: ANN001
        captured.append(cmd)
        if len(captured) == 1:
            return _make_finished(_search_stdout([_search_node(1)], has_next=True, end_cursor="CURSOR_1"))
        return _make_finished(_search_stdout([_search_node(2)], has_next=False))

    with patch("sculptor.web.pr_status.logger") as mock_logger:
        with _patch_cli(handler):
            result = fetch_open_prs_for_token(WORKING_DIR)

    assert [n["number"] for n in result.nodes] == [1, 2]
    assert len(captured) == 2
    assert any(arg == "after=CURSOR_1" for arg in captured[1]), "second page must pass after=<cursor>"
    # Pagination must be logged so silent truncation can't masquerade as full coverage.
    assert mock_logger.warning.called
    assert "pagination" in mock_logger.warning.call_args[0][0]


def test_fetch_open_prs_for_token_missing_rate_limit_is_tolerated() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished(_search_stdout([_search_node(1)], rate_limit=None))

    with _patch_cli(handler):
        result = fetch_open_prs_for_token(WORKING_DIR)

    assert [n["number"] for n in result.nodes] == [1]
    assert result.rate_limit is None


def test_fetch_open_prs_for_token_cli_failure_raises_classified() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished("", returncode=1, stderr="HTTP 403: API rate limit exceeded for user")

    with _patch_cli(handler):
        with pytest.raises(CliStatusError) as exc_info:
            fetch_open_prs_for_token(WORKING_DIR)

    assert exc_info.value.category == "rate_limited"


def test_build_status_from_open_nodes_open_match() -> None:
    node = _search_node(
        100,
        base_ref="main",
        check_state="SUCCESS",
        reviews=[{"state": "APPROVED", "author": {"login": "alice"}}],
        threads=[
            {
                "isResolved": False,
                "comments": {"nodes": [{"author": {"login": "bob"}, "path": "a.py", "line": 3, "body": "fix"}]},
            }
        ],
        mergeable="MERGEABLE",
    )

    result = build_status_from_open_nodes(WORKSPACE_ID, [node], "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 100
    assert result.pipeline_status == "passed"
    assert [a.name for a in result.approvals] == ["alice"]
    assert [c.author for c in result.unresolved_comments] == ["bob"]
    assert result.has_conflicts is False


def test_build_status_from_open_nodes_mismatched_target() -> None:
    node = _search_node(200, base_ref="develop")

    result = build_status_from_open_nodes(WORKSPACE_ID, [node], "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid == 200
    assert result.mismatched_pr_target_branch == "develop"
    assert result.mismatched_pr_web_url == "https://github.com/org/repo/pull/200"


def test_build_status_from_open_nodes_empty() -> None:
    result = build_status_from_open_nodes(WORKSPACE_ID, [], "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid is None


def test_build_status_from_open_nodes_picks_matching_among_two() -> None:
    # Two open PRs on the same source branch targeting different bases; only the
    # one matching the workspace's target should be returned (uses
    # _first_matching_target, which relies on sort:updated ordering).
    nodes = [_search_node(300, base_ref="develop"), _search_node(301, base_ref="main")]

    result = build_status_from_open_nodes(WORKSPACE_ID, nodes, "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 301


def test_build_status_from_open_nodes_conflicting_sets_has_conflicts() -> None:
    node = _search_node(400, base_ref="main", mergeable="CONFLICTING")

    result = build_status_from_open_nodes(WORKSPACE_ID, [node], "origin/main")

    assert result.pr_state == "open"
    assert result.has_conflicts is True


def test_build_status_from_open_nodes_in_merge_queue_sets_flag() -> None:
    # An open PR surfaced through the token-wide search path (the primary path)
    # must carry its merge-queue membership through to is_in_merge_queue.
    node = _search_node(410, base_ref="main", is_in_merge_queue=True)

    result = build_status_from_open_nodes(WORKSPACE_ID, [node], "origin/main")

    assert result.pr_state == "open"
    assert result.is_in_merge_queue is True


# ---------------------------------------------------------------------------
# Cost-regression guard for the production search query (design Risk-4, Goal-2).
#
# GraphQL charges a connection by its parent cardinality times what nests
# beneath it, so an added nested `first:`/`last:` connection silently balloons
# the per-round point cost — and the governor's projections assume a known cost.
# The structural guard below runs always (no `gh`) and fails loudly if a new
# nested connection creeps in; the opt-in live test re-measures the real cost.
# ---------------------------------------------------------------------------


def test_search_query_has_no_unexpected_nested_connections() -> None:
    # The complete set of paginated connections in the production search query.
    # `reviewThreads`/`comments` are the only cost-multiplying nest; adding any
    # other `first:`/`last:` here is what blows up the per-round cost.
    expected_pagination = sorted(
        [
            "first: $prCount",  # search(...) page size
            "last: 1",  # commits(last: 1)
            "first: 20",  # latestReviews — cost-free (no nested connection)
            "first: 10",  # reviewThreads — the dominant cost term (Change-1b)
            "first: 1",  # comments under reviewThreads
        ]
    )
    found = sorted(
        f"{keyword}: {value}" for keyword, value in re.findall(r"\b(first|last):\s*([^\s,)]+)", _SEARCH_PR_QUERY)
    )
    assert found == expected_pagination, (
        f"search query pagination changed: {found} != {expected_pagination}; "
        + "a new nested first:/last: connection would balloon the per-round GraphQL cost"
    )
    # Lock the two page sizes that matter for cost (trimmed) and coverage.
    assert "reviewThreads(first: 10)" in _SEARCH_PR_QUERY
    assert "latestReviews(first: 20)" in _SEARCH_PR_QUERY


# Measured production cost (per design): ~3 points at reviewThreads(first: 10)
# for ~20 open PRs (~7 at first: 30). The ceiling has headroom for fleet-size
# variation; the authority for the governor's projections is this *measured*
# live cost, not the projection itself (Risk-4) — re-measure if it trips.
_SEARCH_QUERY_COST_CEILING = 10


@pytest.mark.skipif(
    not os.environ.get("SCULPTOR_PR_STATUS_LIVE_GH_TEST"),
    reason="opt-in: set SCULPTOR_PR_STATUS_LIVE_GH_TEST=1 to measure cost against real GitHub",
)
def test_search_query_cost_within_band() -> None:
    if shutil.which("gh") is None:
        pytest.skip("gh CLI not available")
    result = run_blocking(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={_SEARCH_PR_QUERY}",
            "-f",
            f"q={_SEARCH_QUERY_STRING}",
            "-F",
            f"prCount={_SEARCH_PAGE_SIZE}",
        ],
        timeout=30.0,
        is_checked=False,
        cwd=Path(__file__).parent,
    )
    assert result.returncode == 0, f"gh api graphql rejected the search query: {result.stderr}"
    payload = json.loads(result.stdout)
    cost = payload["data"]["rateLimit"]["cost"]
    assert cost <= _SEARCH_QUERY_COST_CEILING, (
        f"search query cost {cost} exceeds the expected band (<= {_SEARCH_QUERY_COST_CEILING}); "
        + "re-measure and re-check the governor's projections (design Risk-4)"
    )
