"""Tests for POST /api/v1/workspaces/{workspace_id}/ui/open-file."""

from queue import Queue

from fastapi.testclient import TestClient

from sculptor.database.models import Project
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import OpenFileUiAction
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.ui_actions import add_subscriber as add_ui_action_subscriber
from sculptor.web.ui_actions import remove_subscriber as remove_ui_action_subscriber


def test_ui_open_file_returns_404_for_nonexistent_workspace(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    fake_workspace_id = WorkspaceID()
    response = client.post(
        f"/api/v1/workspaces/{fake_workspace_id}/ui/open-file",
        json={"file_path": "/tmp/anything", "mode": "auto"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "workspace_not_found"


def test_ui_open_file_returns_409_when_workspace_closed(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="ui open-file test workspace",
            transaction=transaction,
        )
        test_services.workspace_service.update_workspace(
            workspace_id=workspace.object_id,
            is_open=False,
            transaction=transaction,
        )

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/ui/open-file",
        json={"file_path": "/tmp/anything", "mode": "auto"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "workspace_not_open"


def test_ui_open_file_returns_400_for_relative_path(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="ui open-file relative path test",
            transaction=transaction,
        )

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/ui/open-file",
        json={"file_path": "relative/path.txt", "mode": "auto"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "file_not_absolute"


def test_ui_open_file_returns_404_for_nonexistent_file(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="ui open-file 404 test",
            transaction=transaction,
        )

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/ui/open-file",
        json={"file_path": "/nonexistent/path/that/does/not/exist.txt", "mode": "auto"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "file_not_found"


def test_ui_open_file_returns_422_for_invalid_mode(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="ui open-file mode test",
            transaction=transaction,
        )

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/ui/open-file",
        json={"file_path": "/tmp/anything", "mode": "bogus"},
    )
    assert response.status_code == 422


def test_ui_open_file_publishes_action_on_success(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: object,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="ui open-file publish test",
            transaction=transaction,
        )

    target_file = test_project.get_local_user_path() / "ui_open_file_target.txt"
    target_file.write_text("hello\n")

    observer_queue: Queue[StreamingUpdateSourceTypes] = Queue()
    add_ui_action_subscriber(observer_queue.put_nowait)
    try:
        response = client.post(
            f"/api/v1/workspaces/{workspace.object_id}/ui/open-file",
            json={"file_path": str(target_file), "mode": "diff"},
        )
    finally:
        remove_ui_action_subscriber(observer_queue.put_nowait)

    assert response.status_code == 204

    published = observer_queue.get_nowait()
    assert isinstance(published, OpenFileUiAction)
    assert published.workspace_id == workspace.object_id
    assert published.file_path == str(target_file)
    assert published.mode == "diff"
