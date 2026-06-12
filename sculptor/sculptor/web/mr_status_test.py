import json
from pathlib import Path
from unittest.mock import patch

from imbue_core.subprocess_utils import FinishedProcess
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.mr_status import fetch_mr_status


def _make_finished(stdout: str, returncode: int = 0) -> FinishedProcess:
    return FinishedProcess(
        stdout=stdout, stderr="", returncode=returncode, command=("glab",), is_output_already_logged=False
    )


WORKSPACE_ID = WorkspaceID()
WORKING_DIR = Path("/tmp/repo")


def _open_mr(iid: int, target_branch: str = "main") -> dict:
    return {
        "iid": iid,
        "title": f"MR !{iid}",
        "target_branch": target_branch,
        "web_url": f"https://gitlab.com/project/-/merge_requests/{iid}",
    }


def _patch_cli(side_effect):  # noqa: ANN001
    return patch("sculptor.web.mr_status.run_cli_with_retry", side_effect=side_effect)


def _is_mr_list(cmd: list) -> bool:
    return cmd[0] == "glab" and cmd[1] == "mr" and cmd[2] == "list"


def _is_mr_view(cmd: list) -> bool:
    return cmd[0] == "glab" and cmd[1] == "mr" and cmd[2] == "view"


def _is_api_call(cmd: list) -> bool:
    return cmd[0] == "glab" and cmd[1] == "api"


def _empty_pipeline_and_details(cmd, _working_dir):  # noqa: ANN001
    """Handle pipeline/approvals/comments calls with empty results."""
    if _is_mr_view(cmd):
        return _make_finished(json.dumps({"pipeline": None}))
    if _is_api_call(cmd):
        if "approvals" in cmd[2]:
            return _make_finished(json.dumps({"approved_by": []}))
        if "discussions" in cmd[2]:
            return _make_finished(json.dumps([]))
    return _make_finished("[]")


# ---------------------------------------------------------------------------
# Open MR with matching target → normal open status
# ---------------------------------------------------------------------------


def test_open_mr_matching_target() -> None:
    mr = _open_mr(100, target_branch="main")

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--merged" not in cmd:
            return _make_finished(json.dumps([mr]))
        if _is_mr_list(cmd) and "--merged" in cmd:
            return _make_finished("[]")
        return _empty_pipeline_and_details(cmd, _working_dir)

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 100
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Open MR with mismatched target → pr_state=none + mismatch fields
# ---------------------------------------------------------------------------


def test_open_mr_mismatched_target() -> None:
    mr = _open_mr(200, target_branch="develop")

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--merged" not in cmd and "--closed" not in cmd:
            return _make_finished(json.dumps([mr]))
        return _make_finished("[]")

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid == 200
    assert result.mismatched_pr_target_branch == "develop"
    assert result.mismatched_pr_web_url == "https://gitlab.com/project/-/merge_requests/200"


# ---------------------------------------------------------------------------
# No MRs at all → pr_state=none, no mismatch
# ---------------------------------------------------------------------------


def test_no_mrs_at_all() -> None:
    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        return _make_finished("[]")

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Merged MR with matching target → pr_state=merged
# ---------------------------------------------------------------------------


def test_merged_mr_matching_target() -> None:
    merged_mr = _open_mr(300, target_branch="main")

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--merged" not in cmd:
            return _make_finished("[]")
        if _is_mr_list(cmd) and "--merged" in cmd:
            return _make_finished(json.dumps([merged_mr]))
        return _make_finished("[]")

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "merged"
    assert result.pr_iid == 300
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Multiple open MRs, one matches target → normal open status
# ---------------------------------------------------------------------------


def test_multiple_open_mrs_one_matches() -> None:
    mrs = [
        _open_mr(400, target_branch="develop"),
        _open_mr(401, target_branch="main"),
    ]

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--merged" not in cmd:
            return _make_finished(json.dumps(mrs))
        if _is_mr_list(cmd) and "--merged" in cmd:
            return _make_finished("[]")
        return _empty_pipeline_and_details(cmd, _working_dir)

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 401
    assert result.mismatched_pr_iid is None


# ---------------------------------------------------------------------------
# Multiple open MRs, none match target → mismatch with first
# ---------------------------------------------------------------------------


def test_multiple_open_mrs_none_match() -> None:
    mrs = [
        _open_mr(500, target_branch="develop"),
        _open_mr(501, target_branch="staging"),
    ]

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--merged" not in cmd and "--closed" not in cmd:
            return _make_finished(json.dumps(mrs))
        return _make_finished("[]")

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "none"
    assert result.mismatched_pr_iid == 500
    assert result.mismatched_pr_target_branch == "develop"


# ---------------------------------------------------------------------------
# origin/ prefix is stripped from target branch
# ---------------------------------------------------------------------------


def test_origin_prefix_stripped() -> None:
    mr = _open_mr(600, target_branch="main")

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--merged" not in cmd:
            return _make_finished(json.dumps([mr]))
        if _is_mr_list(cmd) and "--merged" in cmd:
            return _make_finished("[]")
        return _empty_pipeline_and_details(cmd, _working_dir)

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.pr_iid == 600


# ---------------------------------------------------------------------------
# Open MR with has_conflicts → flag flows through to PrStatusInfo
# ---------------------------------------------------------------------------


def test_open_mr_has_conflicts_flag_flows_through() -> None:
    mr = _open_mr(700, target_branch="main")
    mr["has_conflicts"] = True

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--merged" not in cmd and "--closed" not in cmd:
            return _make_finished(json.dumps([mr]))
        if _is_mr_list(cmd):
            return _make_finished("[]")
        return _empty_pipeline_and_details(cmd, _working_dir)

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "open"
    assert result.has_conflicts is True


# ---------------------------------------------------------------------------
# Closed-not-merged MR with matching target → pr_state=closed
# ---------------------------------------------------------------------------


def test_closed_mr_matching_target() -> None:
    closed_mr = _open_mr(800, target_branch="main")

    def cli_handler(cmd, _working_dir):  # noqa: ANN001
        if _is_mr_list(cmd) and "--closed" in cmd:
            return _make_finished(json.dumps([closed_mr]))
        return _make_finished("[]")

    with _patch_cli(cli_handler):
        result = fetch_mr_status(WORKSPACE_ID, WORKING_DIR, "feat-1", "origin/main")

    assert result.pr_state == "closed"
    assert result.pr_iid == 800
