import shutil
from pathlib import Path

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.tool_names import AgentToolName
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_turn_diff_tracker import JjTurnDiffTracker
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import run_jj


def _count_operations(jj_binary: JjBinary, repo_dir: Path) -> int:
    output = run_jj(jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "-T", 'id ++ "\\n"'), cwd=repo_dir)
    return len(output.splitlines())


@pytest.fixture
def tracker(
    jj_cli: JjCli, jj_workspace: JjWorkspace, test_root_concurrency_group: ConcurrencyGroup
) -> JjTurnDiffTracker:
    return JjTurnDiffTracker(jj_cli, jj_workspace.path, test_root_concurrency_group)


def test_changed_file_paths_are_measured_from_the_last_rebaseline(
    tracker: JjTurnDiffTracker, jj_workspace: JjWorkspace
) -> None:
    (jj_workspace.path / "first.txt").write_text("first\n")
    assert tracker.get_changed_file_paths() == ["first.txt"]

    tracker.rebaseline()
    (jj_workspace.path / "second.txt").write_text("second\n")

    assert tracker.get_changed_file_paths() == ["second.txt"]


def test_changed_file_paths_include_edits_the_agent_committed_with_jj_during_the_turn(
    tracker: JjTurnDiffTracker, jj_binary: JjBinary, jj_workspace: JjWorkspace
) -> None:
    (jj_workspace.path / "committed.txt").write_text("committed\n")
    run_jj(jj_binary, ("commit", "-m", "agent commit"), cwd=jj_workspace.path)
    (jj_workspace.path / "README.md").unlink()

    assert tracker.get_changed_file_paths() == ["README.md", "committed.txt"]


def test_changed_file_paths_are_empty_when_nothing_changed(tracker: JjTurnDiffTracker) -> None:
    assert tracker.get_changed_file_paths() == []


def test_changed_file_paths_are_empty_for_a_stale_workspace(
    tracker: JjTurnDiffTracker, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, jj_workspace.path)

    assert tracker.get_changed_file_paths() == []


def test_rebaselining_an_unchanged_workspace_adds_no_operation(
    tracker: JjTurnDiffTracker, jj_binary: JjBinary, jj_workspace: JjWorkspace
) -> None:
    operations_before = _count_operations(jj_binary, jj_workspace.path)

    tracker.rebaseline()
    tracker.get_changed_file_paths()

    assert _count_operations(jj_binary, jj_workspace.path) == operations_before


def test_compute_diff_for_tool_diffs_an_edit_against_the_baseline_then_against_the_previous_edit(
    tracker: JjTurnDiffTracker, jj_workspace: JjWorkspace
) -> None:
    readme = jj_workspace.path / "README.md"
    readme.write_text("first edit\n")
    first_diff = tracker.compute_diff_for_tool(AgentToolName.EDIT, {"file_path": str(readme)})
    readme.write_text("second edit\n")
    second_diff = tracker.compute_diff_for_tool(AgentToolName.EDIT, {"file_path": str(readme)})

    assert first_diff is not None
    assert "-# jj fixture repo" in first_diff
    assert "+first edit" in first_diff
    assert second_diff is not None
    assert "-first edit" in second_diff
    assert "+second edit" in second_diff


def test_compute_diff_for_tool_shows_a_written_file_as_created(
    tracker: JjTurnDiffTracker, jj_workspace: JjWorkspace
) -> None:
    (jj_workspace.path / "new.txt").write_text("brand new\n")

    diff = tracker.compute_diff_for_tool(AgentToolName.WRITE, {"file_path": "new.txt"})

    assert diff is not None
    assert "new file mode" in diff
    assert "+brand new" in diff


def test_compute_diff_for_tool_measures_from_the_working_copy_as_the_turn_began(
    tracker: JjTurnDiffTracker, jj_workspace: JjWorkspace
) -> None:
    readme = jj_workspace.path / "README.md"
    readme.write_text("before the turn\n")
    tracker.rebaseline()
    readme.write_text("during the turn\n")

    diff = tracker.compute_diff_for_tool(AgentToolName.EDIT, {"file_path": str(readme)})

    assert diff is not None
    assert "-before the turn" in diff
    assert "+during the turn" in diff


def test_compute_diff_for_tool_ignores_tools_and_files_it_cannot_diff(
    tracker: JjTurnDiffTracker, jj_workspace: JjWorkspace, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")

    assert (
        tracker.compute_diff_for_tool(AgentToolName.READ, {"file_path": str(jj_workspace.path / "README.md")}) is None
    )
    assert tracker.compute_diff_for_tool(AgentToolName.EDIT, {}) is None
    assert tracker.compute_diff_for_tool(AgentToolName.EDIT, {"file_path": str(outside)}) is None
    assert tracker.compute_diff_for_tool(AgentToolName.EDIT, {"file_path": "missing.txt"}) is None


def test_to_repo_relative_path_strips_the_checkout_root_and_keeps_outside_paths(
    tracker: JjTurnDiffTracker, jj_workspace: JjWorkspace
) -> None:
    assert tracker.to_repo_relative_path(str(jj_workspace.path / "src" / "module.py")) == "src/module.py"
    assert tracker.to_repo_relative_path("src/module.py") == "src/module.py"
    assert tracker.to_repo_relative_path("/elsewhere/notes.md") == "/elsewhere/notes.md"


def test_a_tracker_for_a_checkout_that_is_gone_reports_no_changes(
    jj_cli: JjCli, jj_workspace: JjWorkspace, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    shutil.rmtree(jj_workspace.path)

    tracker = JjTurnDiffTracker(jj_cli, jj_workspace.path, test_root_concurrency_group)

    assert tracker.get_changed_file_paths() == []
