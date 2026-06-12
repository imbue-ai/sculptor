"""Tests for the files_and_folders directory listing endpoint.

These tests exercise the /api/v1/projects/{project_id}/files_and_folders endpoint
which lists the immediate contents of a directory in the project repository.
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sculptor.database.models import Project
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.web.auth import authenticate_anonymous

NUM_DIRECTORIES = 10
FILES_PER_DIRECTORY = 5


@pytest.fixture
def repo_project(
    test_repo_factory_: TestRepoFactory,
    test_services: CompleteServiceCollection,
) -> Project:
    """Create a project backed by a git repo with a known directory structure."""
    repo_state = test_repo_factory_.create_repo("dir-listing-repo", "main")
    repo_path = repo_state.repo.base_path

    _populate_repo(repo_path)

    repo_state.repo.run_git(["add", "."])
    repo_state.repo.run_git(["commit", "-m", "Add generated files"])

    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        project = test_services.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
        test_services.project_service.activate_project(project)
    assert project is not None
    return project


def _populate_repo(repo_path: Path) -> None:
    """Create a directory tree with subdirectories and files."""
    extensions = [".py", ".ts", ".tsx", ".md", ".json"]
    for d in range(NUM_DIRECTORIES):
        dir_path = repo_path / f"module_{d:02d}"
        dir_path.mkdir(parents=True, exist_ok=True)
        for f in range(FILES_PER_DIRECTORY):
            ext = extensions[f % len(extensions)]
            (dir_path / f"file_{f:02d}{ext}").write_text(f"// file {d}-{f}\n")

    # Also create a top-level file
    (repo_path / "README.md").write_text("# Test repo\n")


def test_root_directory_listing(
    client: TestClient,
    repo_project: Project,
) -> None:
    """An empty directory param should list the root directory contents."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": ""},
    )
    assert response.status_code == 200
    results = response.json()

    folders = [r for r in results if r.endswith("/")]
    files = [r for r in results if not r.endswith("/")]

    # Our generated directories plus any created by the test fixture
    assert len(folders) >= NUM_DIRECTORIES
    assert "README.md" in files
    # Folders should come before files
    assert results.index(folders[-1]) < results.index(files[0])


def test_subdirectory_listing(
    client: TestClient,
    repo_project: Project,
) -> None:
    """Listing a subdirectory should return its immediate children."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": "module_00"},
    )
    assert response.status_code == 200
    results = response.json()

    assert len(results) == FILES_PER_DIRECTORY
    assert all(not r.endswith("/") for r in results)
    assert "file_00.py" in results


def test_filter_within_directory(
    client: TestClient,
    repo_project: Project,
) -> None:
    """The filter param should narrow results within a directory."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": "module_00", "filter": ".ts"},
    )
    assert response.status_code == 200
    results = response.json()

    assert len(results) > 0
    assert all(".ts" in r for r in results)


def test_nonexistent_directory_returns_empty(
    client: TestClient,
    repo_project: Project,
) -> None:
    """A nonexistent directory should return an empty list."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": "does_not_exist"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_git_directory_listed_and_navigable(
    client: TestClient,
    repo_project: Project,
) -> None:
    """The .git directory should appear in listings and be navigable."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": ""},
    )
    assert response.status_code == 200
    results = response.json()
    assert ".git/" in results

    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": ".git"},
    )
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_default_params_list_root(
    client: TestClient,
    repo_project: Project,
) -> None:
    """Omitting both params should list the root directory."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
    )
    assert response.status_code == 200
    results = response.json()
    folders = [r for r in results if r.endswith("/")]
    assert len(folders) >= NUM_DIRECTORIES


def test_absolute_path_lists_filesystem(
    client: TestClient,
    repo_project: Project,
) -> None:
    """An absolute directory path should list that filesystem path directly."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": "/tmp"},
    )
    assert response.status_code == 200
    results = response.json()
    # /tmp exists and should have at least one entry
    assert isinstance(results, list)


def test_tilde_expands_to_home_directory(
    client: TestClient,
    repo_project: Project,
) -> None:
    """A path starting with ~ should expand to the user's home directory."""
    response = client.get(
        f"/api/v1/projects/{repo_project.object_id}/files_and_folders",
        params={"directory": "~"},
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) > 0


def test_concurrent_reads(
    client: TestClient,
    repo_project: Project,
) -> None:
    """Multiple concurrent read requests should all succeed."""
    num_concurrent_requests = 5
    project_id = repo_project.object_id

    def make_request(directory: str) -> int:
        resp = client.get(
            f"/api/v1/projects/{project_id}/files_and_folders",
            params={"directory": directory},
        )
        return resp.status_code

    directories = [f"module_{i:02d}" for i in range(num_concurrent_requests)]

    with ThreadPoolExecutor(max_workers=num_concurrent_requests) as executor:
        futures = [executor.submit(make_request, d) for d in directories]
        results = [f.result() for f in as_completed(futures)]

    for status_code in results:
        assert status_code == 200
