"""Tests for workspace file browser endpoints.

Tests cover:
- GET /api/v1/workspaces/{workspace_id}/files (file listing)
- POST /api/v1/workspaces/{workspace_id}/open-in-os (open in OS)
- POST /api/v1/workspaces/{workspace_id}/read-file-at-ref (read at git ref)
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from sculptor.database.models import Project
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.web.auth import authenticate_anonymous


def _create_workspace(
    transaction: DataModelTransaction,
    services: CompleteServiceCollection,
    project: Project,
) -> Workspace:
    """Create an IN_PLACE workspace for testing."""
    return services.workspace_service.create_workspace(
        project=project,
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        source_branch=None,
        requested_branch_name=None,
        description="file browser test workspace",
        transaction=transaction,
    )


def _git_add_and_commit(repo_path: Path, files: list[str], message: str) -> None:
    """Stage specified files and create a commit in the given repo."""
    for file_path in files:
        subprocess.run(["git", "add", file_path], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True)


def test_workspace_files_returns_files_and_directories(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """File listing returns both files and directories from the workspace repo."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = client.get(f"/api/v1/workspaces/{workspace.object_id}/files")
    assert response.status_code == 200
    data = response.json()
    files_list = data["files"]
    assert len(files_list) > 0
    types_present = {entry["type"] for entry in files_list}
    assert "file" in types_present


def test_workspace_files_excludes_git_directory(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """.git/ entries are excluded from the file listing."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = client.get(f"/api/v1/workspaces/{workspace.object_id}/files")
    assert response.status_code == 200
    data = response.json()
    for entry in data["files"]:
        assert not entry["path"].startswith(".git/"), f"Found .git entry: {entry['path']}"


def test_workspace_files_extracts_directories_from_file_paths(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Parent directories are extracted from file paths and included as directory entries."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    repo_path = test_project.get_local_user_path()
    nested_dir = repo_path / "src" / "components"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "Button.tsx").write_text("export const Button = () => null;\n")

    _git_add_and_commit(repo_path, ["src/components/Button.tsx"], "Add nested file")

    response = client.get(f"/api/v1/workspaces/{workspace.object_id}/files")
    assert response.status_code == 200
    data = response.json()
    directory_paths = {entry["path"] for entry in data["files"] if entry["type"] == "directory"}
    assert "src" in directory_paths
    assert "src/components" in directory_paths


def test_workspace_files_returns_404_for_nonexistent_workspace(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    """Returns 404 when the workspace does not exist."""
    fake_workspace_id = WorkspaceID()
    response = client.get(f"/api/v1/workspaces/{fake_workspace_id}/files")
    assert response.status_code == 404


def test_workspace_files_returns_503_when_git_command_fails(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """When `git ls-files` fails (e.g. transient lock contention), the endpoint
    must return 503 — not 200 with an empty list — so callers can distinguish
    a transient failure from a legitimately empty workspace.
    """
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    # `get_workspace_files` only runs a single git invocation (`git ls-files`),
    # so we can stub the whole helper with a constant non-zero-return triple
    # rather than reaching for a passthrough that would re-trigger the
    # `*args, **kwargs` ratchet.
    failure_triple = (
        128,
        "",
        "fatal: Unable to read index: another git process seems to be running in this repository",
    )

    with patch(
        "sculptor.services.workspace_service.default_implementation.run_git_command_local",
        return_value=failure_triple,
    ):
        response = client.get(f"/api/v1/workspaces/{workspace.object_id}/files")

    assert response.status_code == 503, (
        f"Expected 503 on transient git failure, got {response.status_code}: {response.text}"
    )
    assert response.headers.get("Retry-After") is not None, "503 response should include Retry-After header"


def test_open_in_os_returns_400_for_path_traversal(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Path traversal attempts return 400."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/open-in-os",
        json={"path": "../../../etc/passwd", "action": "open_file"},
    )
    assert response.status_code == 400


def test_open_in_os_returns_404_for_nonexistent_file(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Returns 404 when the file does not exist on disk."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/open-in-os",
        json={"path": "nonexistent_file.txt", "action": "open_file"},
    )
    assert response.status_code == 404


def test_open_in_os_returns_422_for_invalid_action(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Returns 422 for an unrecognized action value (Pydantic Literal validation)."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    repo_path = test_project.get_local_user_path()
    (repo_path / "test_action.txt").write_text("test\n")

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/open-in-os",
        json={"path": "test_action.txt", "action": "invalid_action"},
    )
    assert response.status_code == 422


def test_read_file_at_ref_returns_404_for_nonexistent_file(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Returns 404 when the file does not exist at the given ref."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/read-file-at-ref",
        json={"path": "nonexistent_file_at_ref.txt", "gitRef": "HEAD"},
    )
    assert response.status_code == 404


def test_read_file_at_ref_with_known_committed_file(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Create a file, commit it, and verify read-file-at-ref returns correct content."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    repo_path = test_project.get_local_user_path()
    test_file = repo_path / "ref_test_file.txt"
    test_file.write_text("hello from ref test\n")

    _git_add_and_commit(repo_path, ["ref_test_file.txt"], "Add ref test file")

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/read-file-at-ref",
        json={"path": "ref_test_file.txt", "gitRef": "HEAD"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["encoding"] == "utf-8"
    assert "hello from ref test" in data["content"]
