"""Tests for the routes that register a directory as a project: initialize and init-git."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sculptor.foundation.processes.local_process import run_blocking

_PROJECT_ROUTES = ("/api/v1/projects/initialize", "/api/v1/projects/init-git")


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
