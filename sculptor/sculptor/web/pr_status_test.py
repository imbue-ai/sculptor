import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.pr_status import _GRAPHQL_PR_QUERY
from sculptor.web.pr_status import _PR_QUERY_LIMIT
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
) -> dict:
    """Build one graphql ``pullRequests.nodes`` entry in the given GitHub state.

    Mirrors the shape returned by the single ``gh api graphql`` query the
    backend now issues: identity fields alongside the check/review/comment
    detail (``statusCheckRollup`` is null when no checks have run). ``mergeable``
    is GitHub's ``MERGEABLE`` / ``CONFLICTING`` / ``UNKNOWN`` merge-conflict enum;
    it is included only when provided so unrelated tests keep their minimal shape.
    """
    rollup = {"state": check_state} if check_state is not None else None
    node = {
        "number": number,
        "title": f"PR #{number}",
        "url": f"https://github.com/org/repo/pull/{number}",
        "state": state,
        "baseRefName": base_ref,
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
    # Exactly one CLI call, and it is a `gh api graphql` request (not the old
    # `gh pr list` + `gh pr view` pair).
    assert len(calls) == 1
    assert calls[0][:3] == ["gh", "api", "graphql"]


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
    ):
        assert field in query, f"query is missing field {field!r}"
    # `reviewThreads` is requested directly (it is a valid GraphQL PullRequest
    # field, unlike `gh pr view --json`'s curated subset that shipped the bug).
    assert "reviewThreads" in query


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
    assert result.error_provider == "github"


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
    assert result.error_provider == "github"


def test_secondary_rate_limit_surfaces_error() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished("", returncode=1, stderr="You have exceeded a secondary rate limit.")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.error_category == "rate_limited"
    assert result.error_provider == "github"


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
