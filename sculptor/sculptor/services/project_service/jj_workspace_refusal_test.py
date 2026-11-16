from pathlib import Path

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.project_service.jj_workspace_refusal import ProjectInJjWorkspaceError
from sculptor.services.project_service.jj_workspace_refusal import resolve_project_in_jj_workspace
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import run_jj


@pytest.fixture
def jj(test_root_concurrency_group: ConcurrencyGroup, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv) -> JjCli:
    return JjCli(test_root_concurrency_group, lambda tool: str(jj_binary.path) if tool is Dependency.JJ else None)


def _make_repository_not_colocated_with_git(jj_binary: JjBinary, parent: Path) -> Path:
    """A jj repository whose git store lives inside its `.jj`, so it has no `.git`."""
    repository = parent / "not-colocated"
    repository.mkdir()
    run_jj(jj_binary, ("git", "init", "--no-colocate", str(repository)), cwd=parent)
    return repository


def _add_workspace(jj_binary: JjBinary, repository: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_jj(jj_binary, ("workspace", "add", "--no-colocate", "--name", "secondary", str(destination)), cwd=repository)
    return destination


def test_a_jj_workspace_of_a_colocated_repository_resolves_to_the_repository_root(
    jj: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    assert resolve_project_in_jj_workspace(jj_workspace.path, jj) == jj_colocated_repo.path.resolve()


def test_a_directory_inside_a_jj_workspace_of_a_colocated_repository_resolves_to_the_repository_root(
    jj: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    subdirectory = jj_workspace.path / "src"
    subdirectory.mkdir()

    assert resolve_project_in_jj_workspace(subdirectory, jj) == jj_colocated_repo.path.resolve()


def test_a_symlink_into_a_jj_workspace_of_a_colocated_repository_resolves_to_the_repository_root(
    jj: JjCli, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace, tmp_path: Path
) -> None:
    link = tmp_path / "link-to-workspace"
    link.symlink_to(jj_workspace.path)

    assert resolve_project_in_jj_workspace(link, jj) == jj_colocated_repo.path.resolve()


def test_a_directory_outside_any_jj_workspace_resolves_to_itself(
    jj: JjCli, jj_colocated_repo: JjColocatedRepo, tmp_path: Path
) -> None:
    plain_directory = tmp_path / "plain"
    plain_directory.mkdir()

    assert resolve_project_in_jj_workspace(plain_directory, jj) == plain_directory
    assert resolve_project_in_jj_workspace(jj_colocated_repo.path, jj) == jj_colocated_repo.path


def test_a_jj_workspace_of_a_repository_not_colocated_with_git_is_refused(
    jj: JjCli, jj_binary: JjBinary, tmp_path: Path
) -> None:
    repository = _make_repository_not_colocated_with_git(jj_binary, tmp_path)
    workspace = _add_workspace(jj_binary, repository, tmp_path / "workspaces" / "secondary")

    with pytest.raises(ProjectInJjWorkspaceError) as refusal:
        resolve_project_in_jj_workspace(workspace, jj)

    assert refusal.value.jj_workspace_root == workspace.resolve()


def test_a_repository_not_colocated_with_git_is_refused(jj: JjCli, jj_binary: JjBinary, tmp_path: Path) -> None:
    repository = _make_repository_not_colocated_with_git(jj_binary, tmp_path)

    with pytest.raises(ProjectInJjWorkspaceError) as refusal:
        resolve_project_in_jj_workspace(repository, jj)

    assert refusal.value.jj_workspace_root == repository.resolve()


def test_a_jj_directory_that_links_to_no_store_is_refused(jj: JjCli, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".jj").mkdir(parents=True)

    with pytest.raises(ProjectInJjWorkspaceError):
        resolve_project_in_jj_workspace(workspace, jj)


def test_a_jj_workspace_of_a_colocated_repository_is_refused_while_jj_cannot_run(
    test_root_concurrency_group: ConcurrencyGroup, jj_workspace: JjWorkspace
) -> None:
    jj_not_installed = JjCli(test_root_concurrency_group, lambda tool: None)

    with pytest.raises(ProjectInJjWorkspaceError):
        resolve_project_in_jj_workspace(jj_workspace.path, jj_not_installed)
