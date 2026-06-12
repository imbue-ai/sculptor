import json
from pathlib import Path
from unittest.mock import patch

from imbue_core.subprocess_utils import FinishedProcess
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.pr_status import fetch_pr_status


def _make_finished(stdout: str, returncode: int = 0, stderr: str = "") -> FinishedProcess:
    return FinishedProcess(
        stdout=stdout, stderr=stderr, returncode=returncode, command=("gh",), is_output_already_logged=False
    )


WORKSPACE_ID = WorkspaceID()
WORKING_DIR = Path("/tmp/repo")


def _pr(number: int, state: str, base_ref: str = "main") -> dict:
    """Build one `gh pr list --json ...` row in the given GitHub state."""
    return {
        "number": number,
        "title": f"PR #{number}",
        "baseRefName": base_ref,
        "state": state,
        "url": f"https://github.com/org/repo/pull/{number}",
    }


def _open_pr(number: int, base_ref: str = "main") -> dict:
    return _pr(number, "OPEN", base_ref)


def _merged_pr(number: int, base_ref: str = "main") -> dict:
    return _pr(number, "MERGED", base_ref)


def _closed_pr(number: int, base_ref: str = "main") -> dict:
    return _pr(number, "CLOSED", base_ref)


def _patch_cli(side_effect):  # noqa: ANN001
    return patch("sculptor.web.pr_status.run_cli_with_retry", side_effect=side_effect)


def _pr_list_handler(prs: list[dict]):  # noqa: ANN001
    """Build a cli_handler for the single `gh pr list --state=all` call.

    The backend issues exactly one `gh pr list` query (across all states) and
    then, for an open PR, a single combined `gh pr view` detail call that
    bundles statusCheckRollup / reviews / reviewThreads. This handler returns
    ``prs`` for the list call and an empty combined object for the detail call.
    """

    def handler(cmd, _working_dir):  # noqa: ANN001
        if "list" in cmd:
            return _make_finished(json.dumps(prs))
        if "view" in cmd:
            return _make_finished(json.dumps({"statusCheckRollup": [], "reviews": [], "reviewThreads": []}))
        return _make_finished("[]")

    return handler


# ---------------------------------------------------------------------------
# Open PR with matching target → normal open status
# ---------------------------------------------------------------------------


def test_open_pr_matching_target() -> None:
    with _patch_cli(_pr_list_handler([_open_pr(100, base_ref="main")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 100
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Open PR with mismatched target → pr_state=none + mismatch fields
# ---------------------------------------------------------------------------


def test_open_pr_mismatched_target() -> None:
    with _patch_cli(_pr_list_handler([_open_pr(200, base_ref="develop")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid == 200
    assert result.mismatched_pr_target_branch == "develop"
    assert result.mismatched_pr_web_url == "https://github.com/org/repo/pull/200"


# ---------------------------------------------------------------------------
# No PRs at all → pr_state=none, no mismatch
# ---------------------------------------------------------------------------


def test_no_prs_at_all() -> None:
    with _patch_cli(_pr_list_handler([])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Merged PR with matching target → pr_state=merged
# ---------------------------------------------------------------------------


def test_merged_pr_matching_target() -> None:
    with _patch_cli(_pr_list_handler([_merged_pr(300, base_ref="main")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "merged"
    assert result.pr_iid == 300
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Multiple open PRs, one matches target → normal open status
# ---------------------------------------------------------------------------


def test_multiple_open_prs_one_matches() -> None:
    prs = [
        _open_pr(400, base_ref="develop"),
        _open_pr(401, base_ref="main"),
    ]

    with _patch_cli(_pr_list_handler(prs)):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 401
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Multiple open PRs, none match target → mismatch with first
# ---------------------------------------------------------------------------


def test_multiple_open_prs_none_match() -> None:
    prs = [
        _open_pr(500, base_ref="develop"),
        _open_pr(501, base_ref="staging"),
    ]

    with _patch_cli(_pr_list_handler(prs)):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid == 500
    assert result.mismatched_pr_target_branch == "develop"


# ---------------------------------------------------------------------------
# Closed-not-merged PR with matching target → pr_state=closed
# ---------------------------------------------------------------------------


def test_closed_pr_matching_target() -> None:
    with _patch_cli(_pr_list_handler([_closed_pr(800, base_ref="main")])):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "closed"
    assert result.pr_iid == 800
    assert result.pr_title == "PR #800"
    assert result.pr_web_url == "https://github.com/org/repo/pull/800"


# ---------------------------------------------------------------------------
# Both a merged and a closed PR target this branch → merged wins
# ---------------------------------------------------------------------------


def test_merged_takes_precedence_over_closed() -> None:
    # A branch whose first PR was closed and whose second PR landed: the single
    # --state=all query returns both, and local dispatch must prefer merged.
    prs = [
        _merged_pr(820, base_ref="main"),
        _closed_pr(810, base_ref="main"),
    ]

    with _patch_cli(_pr_list_handler(prs)):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "merged"
    assert result.pr_iid == 820


# ---------------------------------------------------------------------------
# Open PR detail is fetched in a single combined `gh pr view` call
# ---------------------------------------------------------------------------


def test_open_pr_details_fetched_in_single_view_call() -> None:
    view_calls: list[list] = []

    def handler(cmd, _working_dir):  # noqa: ANN001
        if "list" in cmd:
            return _make_finished(json.dumps([_open_pr(42)]))
        if "view" in cmd:
            view_calls.append(cmd)
            return _make_finished(
                json.dumps(
                    {
                        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
                        "reviews": [{"state": "APPROVED", "author": {"login": "alice"}}],
                        "reviewThreads": [
                            {
                                "isResolved": False,
                                "comments": [{"author": {"login": "bob"}, "path": "a.py", "line": 3, "body": "fix"}],
                            }
                        ],
                    }
                )
            )
        return _make_finished("[]")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pipeline_status == "passed"
    assert [a.name for a in result.approvals] == ["alice"]
    assert len(result.unresolved_comments) == 1
    # Exactly one `gh pr view`, and it bundles all three JSON fields in one call.
    assert len(view_calls) == 1
    assert view_calls[0][-1] == "statusCheckRollup,reviews,reviewThreads"


# ---------------------------------------------------------------------------
# A non-rate-limit failure on the detail call still reports the open PR
# ---------------------------------------------------------------------------


def test_open_pr_detail_failure_degrades_gracefully() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        if "list" in cmd:
            return _make_finished(json.dumps([_open_pr(60)]))
        if "view" in cmd:
            return _make_finished("", returncode=1, stderr="HTTP 500 Internal Server Error")
        return _make_finished("[]")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 60
    assert result.pipeline_status is None
    assert result.error_category is None


# ---------------------------------------------------------------------------
# Rate-limit errors surface as a rate_limited category (list and detail calls)
# ---------------------------------------------------------------------------


def test_rate_limit_on_list_surfaces_error() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        if "list" in cmd:
            return _make_finished("", returncode=1, stderr="API rate limit exceeded")
        return _make_finished("[]")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.error_category == "rate_limited"
    assert result.error_provider == "github"


def test_rate_limit_on_detail_surfaces_error() -> None:
    def handler(cmd, _working_dir):  # noqa: ANN001
        if "list" in cmd:
            return _make_finished(json.dumps([_open_pr(70)]))
        if "view" in cmd:
            return _make_finished("", returncode=1, stderr="HTTP 403: API rate limit exceeded for user")
        return _make_finished("[]")

    with _patch_cli(handler):
        result = fetch_pr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.error_category == "rate_limited"
    assert result.error_provider == "github"
