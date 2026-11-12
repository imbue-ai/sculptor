"""Tests for the branch-rename hint that the auto-rename reminder carries."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sculptor.agents.default.claude_code_sdk.branch_rename_hint import BranchRenameHint
from sculptor.agents.default.claude_code_sdk.branch_rename_hint import resolve_branch_rename_hint
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.services.workspace_service.vcs.errors import GitCommandInJjWorkspaceError

_PLACEHOLDER_BRANCH = "dev/gorgeous-emu"


def _make_repo(path: Path, user_name: str) -> None:
    """Create a repo with one commit on `main` whose git user.name is `user_name`."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", user_name], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=path, check=True, capture_output=True)
    (path / "file.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=path, check=True, capture_output=True)


def _wrap(environment: LocalEnvironment) -> LocalAgentExecutionEnvironment:
    dep_service = DependencyManagementService.model_construct(concurrency_group=MagicMock(spec=ConcurrencyGroup))
    return LocalAgentExecutionEnvironment(environment, TaskID(), dep_service)


def _in_place_environment(repo: Path, concurrency_group: ConcurrencyGroup) -> LocalAgentExecutionEnvironment:
    environment = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(repo)),
        project_id=ProjectID(),
        concurrency_group=concurrency_group,
        repo_host_path=repo,
    )
    return _wrap(environment)


def _worktree_environment(
    workspace_dir: Path, repo: Path, concurrency_group: ConcurrencyGroup, branch: str
) -> LocalAgentExecutionEnvironment:
    environment = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(workspace_dir)),
        project_id=ProjectID(),
        concurrency_group=concurrency_group,
        repo_host_path=repo,
        initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
        source_branch="main",
        requested_branch_name=branch,
    )
    return _wrap(environment)


def test_in_place_workspace_never_gets_a_hint(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, "Dev Person")
    environment = _in_place_environment(repo, test_root_concurrency_group)

    assert resolve_branch_rename_hint(environment, "<user>/<slug>") is None


def test_worktree_placeholder_branch_gets_the_resolved_template(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, "Dev Person")
    environment = _worktree_environment(tmp_path / "workspace", repo, test_root_concurrency_group, _PLACEHOLDER_BRANCH)

    hint = resolve_branch_rename_hint(environment, "<user>/<slug>")

    assert hint == BranchRenameHint(current_branch=_PLACEHOLDER_BRANCH, target_template="dev/<slug>")


def test_branch_outside_the_pattern_gets_no_hint(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, "Dev Person")
    environment = _worktree_environment(tmp_path / "workspace", repo, test_root_concurrency_group, _PLACEHOLDER_BRANCH)

    assert resolve_branch_rename_hint(environment, "feature/<slug>") is None


def test_pattern_without_a_slug_placeholder_gets_no_hint(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, "Dev Person")
    environment = _worktree_environment(tmp_path / "workspace", repo, test_root_concurrency_group, _PLACEHOLDER_BRANCH)

    assert resolve_branch_rename_hint(environment, "<user>/fixed") is None


def test_detached_head_gets_no_hint(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, "Dev Person")
    environment = _worktree_environment(tmp_path / "workspace", repo, test_root_concurrency_group, _PLACEHOLDER_BRANCH)
    subprocess.run(
        ["git", "checkout", "--detach"],
        cwd=environment.get_working_directory(),
        check=True,
        capture_output=True,
    )

    assert resolve_branch_rename_hint(environment, "<user>/<slug>") is None


def test_hint_reads_the_git_user_through_the_project_env_variables(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo, "Dev Person")
    environment = _worktree_environment(
        tmp_path / "workspace", repo, test_root_concurrency_group, "agent/gorgeous-emu"
    )
    env_file = environment.get_working_directory() / ".sculptor" / ".env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("GIT_CONFIG_COUNT=1\nGIT_CONFIG_KEY_0=user.name\nGIT_CONFIG_VALUE_0=Agent\n")

    hint = resolve_branch_rename_hint(environment, "<user>/<slug>")

    assert hint == BranchRenameHint(current_branch="agent/gorgeous-emu", target_template="agent/<slug>")


def test_jj_workspace_raises_the_tripwire_instead_of_giving_no_hint(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    workspace_dir = tmp_path / "workspace"
    (workspace_dir / "code" / ".jj").mkdir(parents=True)
    environment = LocalEnvironment(
        environment_id=LocalEnvironmentID(str(workspace_dir)),
        project_id=ProjectID(),
        concurrency_group=test_root_concurrency_group,
        repo_host_path=tmp_path / "repo",
        initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
    )

    with pytest.raises(GitCommandInJjWorkspaceError):
        resolve_branch_rename_hint(_wrap(environment), "<user>/<slug>")
