"""Tests for POST /api/v1/workspaces/{workspace_id}/ui/webview/{navigate,refresh}."""

from queue import Queue

from fastapi.testclient import TestClient

from sculptor.database.models import Project
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WebviewCommandUiAction
from sculptor.web.ui_actions import add_subscriber as add_ui_action_subscriber
from sculptor.web.ui_actions import remove_subscriber as remove_ui_action_subscriber


def _create_open_workspace(
    test_services: CompleteServiceCollection,
    test_project: Project,
    description: str,
) -> WorkspaceID:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description=description,
            transaction=transaction,
        )
    return workspace.object_id


def test_webview_navigate_returns_404_for_nonexistent_workspace(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    fake_workspace_id = WorkspaceID()
    response = client.post(
        f"/api/v1/workspaces/{fake_workspace_id}/ui/webview/navigate",
        json={"url": "file:///tmp/x.html"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "workspace_not_found"


def test_webview_refresh_returns_404_for_nonexistent_workspace(
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    fake_workspace_id = WorkspaceID()
    response = client.post(
        f"/api/v1/workspaces/{fake_workspace_id}/ui/webview/refresh",
        json={},
    )
    assert response.status_code == 404


def test_webview_navigate_rejects_empty_url(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    workspace_id = _create_open_workspace(test_services, test_project, "webview-empty-url")
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/ui/webview/navigate",
        json={"url": ""},
    )
    assert response.status_code == 422


def test_webview_navigate_publishes_action_on_success(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    workspace_id = _create_open_workspace(test_services, test_project, "webview-navigate-publish")
    observer_queue: Queue[StreamingUpdateSourceTypes] = Queue()
    add_ui_action_subscriber(observer_queue.put_nowait)
    try:
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/ui/webview/navigate",
            json={"url": "file:///tmp/page.html"},
        )
    finally:
        remove_ui_action_subscriber(observer_queue.put_nowait)

    assert response.status_code == 204
    published = observer_queue.get_nowait()
    assert isinstance(published, WebviewCommandUiAction)
    assert published.workspace_id == workspace_id
    assert published.kind == "navigate"
    assert published.url == "file:///tmp/page.html"
    assert published.seq == 1


def test_webview_refresh_publishes_action_on_success(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    workspace_id = _create_open_workspace(test_services, test_project, "webview-refresh-publish")
    observer_queue: Queue[StreamingUpdateSourceTypes] = Queue()
    add_ui_action_subscriber(observer_queue.put_nowait)
    try:
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/ui/webview/refresh",
            json={},
        )
    finally:
        remove_ui_action_subscriber(observer_queue.put_nowait)

    assert response.status_code == 204
    published = observer_queue.get_nowait()
    assert isinstance(published, WebviewCommandUiAction)
    assert published.workspace_id == workspace_id
    assert published.kind == "refresh"
    assert published.url is None


def test_webview_seq_increments_per_workspace(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    workspace_id = _create_open_workspace(test_services, test_project, "webview-seq-monotonic")
    observer_queue: Queue[StreamingUpdateSourceTypes] = Queue()
    add_ui_action_subscriber(observer_queue.put_nowait)
    try:
        client.post(
            f"/api/v1/workspaces/{workspace_id}/ui/webview/navigate",
            json={"url": "file:///tmp/a.html"},
        )
        client.post(
            f"/api/v1/workspaces/{workspace_id}/ui/webview/refresh",
            json={},
        )
        client.post(
            f"/api/v1/workspaces/{workspace_id}/ui/webview/navigate",
            json={"url": "file:///tmp/b.html"},
        )
    finally:
        remove_ui_action_subscriber(observer_queue.put_nowait)

    first = observer_queue.get_nowait()
    second = observer_queue.get_nowait()
    third = observer_queue.get_nowait()
    assert isinstance(first, WebviewCommandUiAction)
    assert isinstance(second, WebviewCommandUiAction)
    assert isinstance(third, WebviewCommandUiAction)
    assert first.seq < second.seq < third.seq
