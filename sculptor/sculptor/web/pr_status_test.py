import json
from pathlib import Path
from unittest.mock import patch

from sculptor.foundation.subprocess_utils import FinishedProcess
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.pr_status import fetch_pr_status


def _make_finished(stdout: str, returncode: int = 0) -> FinishedProcess:
    return FinishedProcess(
        stdout=stdout, stderr="", returncode=returncode, command=("gh",), is_output_already_logged=False
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

    The backend now issues exactly one `gh pr list` query (across all states)
    and then, for an open PR, follows up with per-PR detail calls
    (statusCheckRollup / reviews / reviewThreads). This handler returns ``prs``
    for the list call and empty results for the detail calls.
    """

    def handler(cmd, _working_dir):  # noqa: ANN001
        if "list" in cmd:
            return _make_finished(json.dumps(prs))
        if "statusCheckRollup" in str(cmd):
            return _make_finished(json.dumps({"statusCheckRollup": []}))
        if "reviews" in str(cmd):
            return _make_finished(json.dumps({"reviews": []}))
        if "reviewThreads" in str(cmd):
            return _make_finished(json.dumps({"reviewThreads": []}))
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
