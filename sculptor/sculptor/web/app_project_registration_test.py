"""Tests for the routes that register a directory as a project."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sculptor.config.user_config import DependencyPaths
from sculptor.database.models import Project
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import run_jj

_PROJECT_ROUTES = (
    "/api/v1/projects/initialize",
    "/api/v1/projects/init-git",
    "/api/v1/projects/create-initial-commit",
)


@pytest.fixture
def jj_resolved_to_the_pinned_binary(jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv) -> Iterator[None]:
    set_user_config_instance(
        get_default_user_config_instance().model_copy(
            update={"dependency_paths": DependencyPaths(jj=str(jj_binary.path))}
        )
    )
    yield
    set_user_config_instance(None)


@pytest.fixture
def jj_found_nowhere(jj_isolated_env: JjIsolatedEnv) -> Iterator[None]:
    set_user_config_instance(
        get_default_user_config_instance().model_copy(update={"dependency_paths": DependencyPaths(jj="CUSTOM")})
    )
    yield
    set_user_config_instance(None)


def _make_jj_workspace(path: Path) -> Path:
    """A directory with `.jj` and no `.git`, the shape of a jj workspace."""
    (path / ".jj").mkdir(parents=True)
    return path


@pytest.mark.parametrize("route", _PROJECT_ROUTES)
def test_project_routes_refuse_a_jj_workspace_without_creating_a_git_repository(
    route: str, client: TestClient, tmp_path: Path
) -> None:
    jj_workspace = _make_jj_workspace(tmp_path / "jj-workspace")

    response = client.post(route, json={"project_path": str(jj_workspace)})

    assert response.status_code == 400
    assert "jj workspace" in response.json()["detail"]
    assert not (jj_workspace / ".git").exists()


@pytest.mark.parametrize("route", _PROJECT_ROUTES)
def test_project_routes_refuse_a_directory_inside_a_jj_workspace(
    route: str, client: TestClient, tmp_path: Path
) -> None:
    jj_workspace = _make_jj_workspace(tmp_path / "jj-workspace")
    subdirectory = jj_workspace / "src"
    subdirectory.mkdir()

    response = client.post(route, json={"project_path": str(subdirectory)})

    assert response.status_code == 400
    assert str(jj_workspace) in response.json()["detail"]
    assert not (subdirectory / ".git").exists()


@pytest.mark.parametrize("route", _PROJECT_ROUTES)
def test_project_routes_refuse_a_symlink_into_a_jj_workspace(route: str, client: TestClient, tmp_path: Path) -> None:
    jj_workspace = _make_jj_workspace(tmp_path / "jj-workspace")
    subdirectory = jj_workspace / "src"
    subdirectory.mkdir()
    link = tmp_path / "link-to-src"
    link.symlink_to(subdirectory)

    response = client.post(route, json={"project_path": str(link)})

    assert response.status_code == 400
    assert str(jj_workspace) in response.json()["detail"]
    assert not (subdirectory / ".git").exists()


def test_create_initial_commit_in_a_jj_workspace_inside_a_git_repository_commits_nothing(
    client: TestClient, tmp_path: Path
) -> None:
    git_repository = tmp_path / "git-repository"
    git_repository.mkdir()
    run_blocking(["git", "init", "-q", "-b", "main"], cwd=git_repository)
    run_blocking(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=git_repository,
    )
    jj_workspace = _make_jj_workspace(git_repository / "jj-workspace")
    (jj_workspace / "file.txt").write_text("content\n")

    response = client.post("/api/v1/projects/create-initial-commit", json={"project_path": str(jj_workspace)})

    assert response.status_code == 400
    assert "jj workspace" in response.json()["detail"]
    commit_count = run_blocking(["git", "rev-list", "--count", "HEAD"], cwd=git_repository).stdout.strip()
    assert commit_count == "1"


def test_initialize_accepts_a_repository_colocated_with_jj(client: TestClient, tmp_path: Path) -> None:
    colocated_repo = tmp_path / "colocated"
    colocated_repo.mkdir()
    run_blocking(["git", "init", "-q", "-b", "main"], cwd=colocated_repo)
    run_blocking(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=colocated_repo,
    )
    (colocated_repo / ".jj").mkdir()

    response = client.post("/api/v1/projects/initialize", json={"project_path": str(colocated_repo)})

    assert response.status_code == 200


@pytest.mark.parametrize("relative_path", ["", "src"], ids=["workspace_root", "subdirectory"])
def test_initialize_registers_the_colocated_repository_for_a_path_inside_its_jj_workspace(
    relative_path: str,
    client: TestClient,
    jj_resolved_to_the_pinned_binary: None,
    jj_colocated_repo: JjColocatedRepo,
    jj_workspace: JjWorkspace,
) -> None:
    project_path = jj_workspace.path / relative_path
    project_path.mkdir(exist_ok=True)

    response = client.post("/api/v1/projects/initialize", json={"project_path": str(project_path)})

    assert response.status_code == 200
    project = Project.model_validate(response.json())
    assert project.get_local_user_path() == jj_colocated_repo.path.resolve()


def test_initialize_refuses_a_jj_workspace_of_a_repository_not_colocated_with_git(
    client: TestClient, jj_resolved_to_the_pinned_binary: None, jj_binary: JjBinary, tmp_path: Path
) -> None:
    repository = tmp_path / "not-colocated"
    repository.mkdir()
    run_jj(jj_binary, ("git", "init", "--no-colocate", str(repository)), cwd=tmp_path)
    jj_workspace = tmp_path / "secondary"
    run_jj(jj_binary, ("workspace", "add", "--no-colocate", "--name", "secondary", str(jj_workspace)), cwd=repository)

    response = client.post("/api/v1/projects/initialize", json={"project_path": str(jj_workspace)})

    assert response.status_code == 400
    assert "jj workspace" in response.json()["detail"]
    assert not (jj_workspace / ".git").exists()
    assert not (repository / ".git").exists()


@pytest.mark.parametrize("route", ["/api/v1/projects/init-git", "/api/v1/projects/create-initial-commit"])
def test_routes_that_create_a_git_repository_refuse_a_jj_workspace_of_a_colocated_repository(
    route: str,
    client: TestClient,
    jj_resolved_to_the_pinned_binary: None,
    jj_colocated_repo: JjColocatedRepo,
    jj_workspace: JjWorkspace,
) -> None:
    (jj_workspace.path / "new-file.txt").write_text("content\n")
    commit_count_before = run_blocking(["git", "rev-list", "--count", "--all"], cwd=jj_colocated_repo.path).stdout

    response = client.post(route, json={"project_path": str(jj_workspace.path)})

    assert response.status_code == 400
    assert str(jj_workspace.path.resolve()) in response.json()["detail"]
    assert not (jj_workspace.path / ".git").exists()
    commit_count_after = run_blocking(["git", "rev-list", "--count", "--all"], cwd=jj_colocated_repo.path).stdout
    assert commit_count_after == commit_count_before


def test_initialize_says_it_needs_a_working_jj_when_it_finds_none_for_a_jj_workspace(
    client: TestClient, jj_workspace: JjWorkspace, jj_found_nowhere: None
) -> None:
    response = client.post("/api/v1/projects/initialize", json={"project_path": str(jj_workspace.path)})

    assert response.status_code == 400
    assert (
        "Sculptor needs a working jj to find that workspace's repository, but jj is not installed"
        in (response.json()["detail"])
    )
