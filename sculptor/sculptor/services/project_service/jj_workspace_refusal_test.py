from collections.abc import Iterator
from pathlib import Path

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.project_service.jj_workspace_refusal import JjUnusableForProjectError
from sculptor.services.project_service.jj_workspace_refusal import ProjectInJjWorkspaceError
from sculptor.services.project_service.jj_workspace_refusal import resolve_project_in_jj_workspace
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.vcs_runners import build_vcs_runners
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import run_jj


def _use_jj(jj_value: str) -> None:
    set_user_config_instance(
        get_default_user_config_instance().model_copy(update={"dependency_paths": DependencyPaths(jj=jj_value)})
    )


@pytest.fixture
def dependency_management_service() -> Iterator[DependencyManagementService]:
    with ConcurrencyGroup(name="dependency_management_service") as concurrency_group:
        yield DependencyManagementService(concurrency_group=concurrency_group)
    set_user_config_instance(None)


def _make_jj(concurrency_group: ConcurrencyGroup, dependency_management_service: DependencyManagementService) -> JjCli:
    return build_vcs_runners(concurrency_group, dependency_management_service.resolve_binary_path).jj


@pytest.fixture
def jj(
    test_root_concurrency_group: ConcurrencyGroup,
    dependency_management_service: DependencyManagementService,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
) -> JjCli:
    """A runner for the pinned jj, which the dependency service also resolves."""
    _use_jj(str(jj_binary.path))
    return _make_jj(test_root_concurrency_group, dependency_management_service)


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
    jj: JjCli,
    dependency_management_service: DependencyManagementService,
    jj_colocated_repo: JjColocatedRepo,
    jj_workspace: JjWorkspace,
) -> None:
    assert (
        resolve_project_in_jj_workspace(jj_workspace.path, jj, dependency_management_service)
        == jj_colocated_repo.path.resolve()
    )


def test_a_directory_inside_a_jj_workspace_of_a_colocated_repository_resolves_to_the_repository_root(
    jj: JjCli,
    dependency_management_service: DependencyManagementService,
    jj_colocated_repo: JjColocatedRepo,
    jj_workspace: JjWorkspace,
) -> None:
    subdirectory = jj_workspace.path / "src"
    subdirectory.mkdir()

    assert (
        resolve_project_in_jj_workspace(subdirectory, jj, dependency_management_service)
        == jj_colocated_repo.path.resolve()
    )


def test_a_symlink_into_a_jj_workspace_of_a_colocated_repository_resolves_to_the_repository_root(
    jj: JjCli,
    dependency_management_service: DependencyManagementService,
    jj_colocated_repo: JjColocatedRepo,
    jj_workspace: JjWorkspace,
    tmp_path: Path,
) -> None:
    link = tmp_path / "link-to-workspace"
    link.symlink_to(jj_workspace.path)

    assert resolve_project_in_jj_workspace(link, jj, dependency_management_service) == jj_colocated_repo.path.resolve()


def test_a_directory_outside_any_jj_workspace_resolves_to_itself(
    jj: JjCli,
    dependency_management_service: DependencyManagementService,
    jj_colocated_repo: JjColocatedRepo,
    tmp_path: Path,
) -> None:
    plain_directory = tmp_path / "plain"
    plain_directory.mkdir()

    assert resolve_project_in_jj_workspace(plain_directory, jj, dependency_management_service) == plain_directory
    assert (
        resolve_project_in_jj_workspace(jj_colocated_repo.path, jj, dependency_management_service)
        == jj_colocated_repo.path
    )


def test_a_jj_workspace_of_a_repository_not_colocated_with_git_is_refused(
    jj: JjCli, dependency_management_service: DependencyManagementService, jj_binary: JjBinary, tmp_path: Path
) -> None:
    repository = _make_repository_not_colocated_with_git(jj_binary, tmp_path)
    workspace = _add_workspace(jj_binary, repository, tmp_path / "workspaces" / "secondary")

    with pytest.raises(ProjectInJjWorkspaceError) as refusal:
        resolve_project_in_jj_workspace(workspace, jj, dependency_management_service)

    assert refusal.value.jj_workspace_root == workspace.resolve()


def test_a_repository_not_colocated_with_git_is_refused(
    jj: JjCli, dependency_management_service: DependencyManagementService, jj_binary: JjBinary, tmp_path: Path
) -> None:
    repository = _make_repository_not_colocated_with_git(jj_binary, tmp_path)

    with pytest.raises(ProjectInJjWorkspaceError) as refusal:
        resolve_project_in_jj_workspace(repository, jj, dependency_management_service)

    assert refusal.value.jj_workspace_root == repository.resolve()


def test_a_jj_directory_that_links_to_no_store_is_refused(
    jj: JjCli, dependency_management_service: DependencyManagementService, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".jj").mkdir(parents=True)

    with pytest.raises(ProjectInJjWorkspaceError):
        resolve_project_in_jj_workspace(workspace, jj, dependency_management_service)


def test_a_jj_workspace_of_a_colocated_repository_is_refused_as_needing_jj_while_none_is_found(
    test_root_concurrency_group: ConcurrencyGroup,
    dependency_management_service: DependencyManagementService,
    jj_workspace: JjWorkspace,
) -> None:
    _use_jj("CUSTOM")
    jj_not_installed = _make_jj(test_root_concurrency_group, dependency_management_service)

    with pytest.raises(JjUnusableForProjectError) as refusal:
        resolve_project_in_jj_workspace(jj_workspace.path, jj_not_installed, dependency_management_service)

    assert str(refusal.value) == (
        f"Selected directory is inside the jj workspace at {jj_workspace.path.resolve()}. "
        + "Sculptor needs a working jj to find that workspace's repository, "
        + "but jj is not installed: install it or set its path on the Jujutsu settings page."
    )
