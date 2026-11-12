import shutil
from pathlib import Path

from sculptor.config.user_config import DependencyPaths
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.interfaces.agents.tool_names import AgentToolName
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.services.workspace_service.vcs.turn_diff_tracker import make_turn_diff_tracker


def _in_place_environment(
    repo: Path, workspace: Path, concurrency_group: ConcurrencyGroup
) -> LocalAgentExecutionEnvironment:
    """An agent environment working in `repo` that keeps its own files in `workspace`, outside the checkout."""
    local_environment = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(workspace)),
        project_id=ProjectID(),
        concurrency_group=concurrency_group,
        repo_host_path=repo,
        sculptor_folder=workspace / "sculptor_folder",
    )
    dependency_management_service = DependencyManagementService(
        concurrency_group=concurrency_group.make_concurrency_group("dependency_management_service"),
    )
    return LocalAgentExecutionEnvironment(local_environment, TaskID(), dependency_management_service)


def test_changed_file_paths_are_measured_from_the_last_rebaseline(
    git_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _in_place_environment(git_repo, tmp_path / "workspace", test_root_concurrency_group)
    tracker = make_turn_diff_tracker(environment)
    (git_repo / "first.txt").write_text("first\n")
    assert tracker.get_changed_file_paths() == ["first.txt"]
    run_blocking(["git", "add", "first.txt"], cwd=git_repo)
    run_blocking(["git", "commit", "-q", "-m", "first"], cwd=git_repo)

    tracker.rebaseline()
    (git_repo / "second.txt").write_text("second\n")

    assert tracker.get_changed_file_paths() == ["second.txt"]


def test_changed_file_paths_after_rebaselining_on_uncommitted_changes(
    git_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _in_place_environment(git_repo, tmp_path / "workspace", test_root_concurrency_group)
    tracker = make_turn_diff_tracker(environment)
    (git_repo / "first.txt").write_text("first\n")
    assert tracker.get_changed_file_paths() == ["first.txt"]

    tracker.rebaseline()
    (git_repo / "second.txt").write_text("second\n")

    assert tracker.get_changed_file_paths() == ["second.txt"]


def test_changed_file_paths_include_a_lone_unstaged_edit_to_a_tracked_file(
    git_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _in_place_environment(git_repo, tmp_path / "workspace", test_root_concurrency_group)
    tracker = make_turn_diff_tracker(environment)

    (git_repo / "file.txt").write_text("edited\n")

    assert tracker.get_changed_file_paths() == ["file.txt"]


def test_tool_diff_after_rebaselining_on_an_unstaged_edit_is_measured_from_that_baseline(
    git_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _in_place_environment(git_repo, tmp_path / "workspace", test_root_concurrency_group)
    tracker = make_turn_diff_tracker(environment)
    (git_repo / "file.txt").write_text("uncommitted\n")
    tracker.rebaseline()
    (git_repo / "file.txt").write_text("edited\n")

    diff = tracker.compute_diff_for_tool(AgentToolName.EDIT, {"file_path": str(git_repo / "file.txt")})

    assert diff is not None
    assert "-uncommitted" in diff
    assert "+edited" in diff


def test_to_repo_relative_path_strips_the_checkout_root_and_keeps_outside_paths(
    git_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _in_place_environment(git_repo, tmp_path / "workspace", test_root_concurrency_group)
    tracker = make_turn_diff_tracker(environment)

    assert tracker.to_repo_relative_path(str(git_repo / "src" / "module.py")) == "src/module.py"
    assert tracker.to_repo_relative_path("/elsewhere/notes.md") == "/elsewhere/notes.md"


def test_tracker_runs_git_with_the_binary_the_environment_resolves(
    git_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    invocation_log = tmp_path / "git_invocations.log"
    logging_git = tmp_path / "logging_git"
    logging_git.write_text(f'#!/bin/bash\necho "$@" >> {invocation_log}\nexec {shutil.which("git")} "$@"\n')
    logging_git.chmod(0o755)
    config = get_default_user_config_instance().model_copy(
        update={"dependency_paths": DependencyPaths(git=str(logging_git))}
    )
    set_user_config_instance(config)
    environment = _in_place_environment(git_repo, tmp_path / "workspace", test_root_concurrency_group)

    make_turn_diff_tracker(environment)

    assert "status --porcelain" in invocation_log.read_text()


def test_tracker_sees_the_checkout_through_the_project_env_variables(
    git_repo: Path, tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    (git_repo / ".git" / "info" / "exclude").write_text(".sculptor/\n")
    excludes_file = tmp_path / "agent_excludes"
    excludes_file.write_text("*.log\n")
    env_file = git_repo / ".sculptor" / ".env"
    env_file.parent.mkdir()
    env_file.write_text(
        f"GIT_CONFIG_COUNT=1\nGIT_CONFIG_KEY_0=core.excludesFile\nGIT_CONFIG_VALUE_0={excludes_file}\n"
    )
    environment = _in_place_environment(git_repo, tmp_path / "workspace", test_root_concurrency_group)
    tracker = make_turn_diff_tracker(environment)

    (git_repo / "debug.log").write_text("noise\n")
    (git_repo / "notes.txt").write_text("kept\n")

    assert tracker.get_changed_file_paths() == ["notes.txt"]
