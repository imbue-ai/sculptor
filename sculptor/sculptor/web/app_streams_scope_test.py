# ruff: noqa: F811
import pytest
import requests

from sculptor.database.models import Project
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.web.app_basic_test import _create_task_with_message_in_workspace
from sculptor.web.app_basic_test import _create_workspace
from sculptor.web.app_streams_test import _next_streaming_update
from sculptor.web.app_streams_test import server_app  # noqa: F401
from sculptor.web.app_streams_test import server_url  # noqa: F401
from sculptor.web.app_streams_test import stream_response
from sculptor.web.auth import authenticate_anonymous


def _request_upgrade_status(server_url: str, scope_value: str) -> int:
    """Issue an HTTP GET with WS upgrade headers; return the actual HTTP status."""
    response = requests.get(
        server_url + "/api/v1/stream/ws",
        params={"scope": scope_value},
        headers={
            "Upgrade": "websocket",
            "Connection": "upgrade",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            "Sec-WebSocket-Version": "13",
        },
        allow_redirects=False,
    )
    return response.status_code


def test_no_scope_param_works_as_before(server_url: str) -> None:
    stream_url = server_url + "/api/v1/stream/ws"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert isinstance(update, dict)


def test_scope_all_works(server_url: str) -> None:
    stream_url = server_url + "/api/v1/stream/ws?scope=all"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert isinstance(update, dict)


def test_scope_project_works(server_url: str, test_services: CompleteServiceCollection, test_project: Project) -> None:
    stream_url = server_url + f"/api/v1/stream/ws?scope=project:{test_project.object_id}"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert isinstance(update, dict)


def test_scope_workspace_works(
    server_url: str, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    stream_url = server_url + f"/api/v1/stream/ws?scope=workspace:{workspace.object_id}"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert isinstance(update, dict)


def test_scope_agent_works(server_url: str, test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )

    stream_url = server_url + f"/api/v1/stream/ws?scope=agent:{task.object_id}"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert isinstance(update, dict)


@pytest.mark.parametrize("scope_value", ["junk", "agent:", ":foo", "foo:bar", "all:foo"])
def test_scope_malformed_returns_400(server_url: str, scope_value: str) -> None:
    assert _request_upgrade_status(server_url, scope_value) == 400


def test_scope_agent_unknown_returns_404(server_url: str) -> None:
    assert _request_upgrade_status(server_url, "agent:tsk_01h0000000000000000000000a") == 404


def test_scope_workspace_unknown_returns_404(server_url: str) -> None:
    assert _request_upgrade_status(server_url, "workspace:ws_01h0000000000000000000000a") == 404


def test_scope_project_unknown_returns_404(server_url: str) -> None:
    assert _request_upgrade_status(server_url, "project:prj_01h0000000000000000000000a") == 404


def test_multiple_scope_params_returns_400(server_url: str) -> None:
    """A request with more than one ?scope= must be rejected at
    the upgrade. requests sends a list as repeated query params, not a single
    comma-joined value, which is exactly the case we need to test.
    """
    response = requests.get(
        server_url + "/api/v1/stream/ws",
        params=[("scope", "all"), ("scope", "agent:tsk_01h0000000000000000000000a")],
        headers={
            "Upgrade": "websocket",
            "Connection": "upgrade",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            "Sec-WebSocket-Version": "13",
        },
        allow_redirects=False,
    )
    assert response.status_code == 400


def test_agent_scope_initial_frame_has_only_subscribed_agent(
    server_url: str, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace_a = _create_workspace(transaction, test_services, test_project, description="ws-a")
        workspace_b = _create_workspace(transaction, test_services, test_project, description="ws-b")
        task_a = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace_a
        )
        _create_task_with_message_in_workspace(transaction, user_session, test_project, test_services, workspace_b)

    stream_url = server_url + f"/api/v1/stream/ws?scope=agent:{task_a.object_id}"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert set(update.get("taskViewsByTaskId", {}).keys()) == {str(task_a.object_id)}
        assert update.get("userUpdate", {}).get("projects") in (None, [], ())


def test_workspace_scope_initial_frame_has_only_workspace_data(
    server_url: str, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace_a = _create_workspace(transaction, test_services, test_project, description="ws-a")
        workspace_b = _create_workspace(transaction, test_services, test_project, description="ws-b")
        task_a = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace_a
        )
        _create_task_with_message_in_workspace(transaction, user_session, test_project, test_services, workspace_b)

    stream_url = server_url + f"/api/v1/stream/ws?scope=workspace:{workspace_a.object_id}"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert set(update.get("taskViewsByTaskId", {}).keys()) == {str(task_a.object_id)}
        workspace_branch = update.get("workspaceBranchByWorkspaceId", {})
        assert str(workspace_b.object_id) not in workspace_branch


def test_project_scope_initial_frame_has_only_project_data(
    server_url: str, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )

    stream_url = server_url + f"/api/v1/stream/ws?scope=project:{test_project.object_id}"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert str(task.object_id) in update.get("taskViewsByTaskId", {})


def test_all_scope_matches_existing_unscoped_behavior(
    server_url: str, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )

    stream_url = server_url + "/api/v1/stream/ws?scope=all"
    with stream_response(stream_url) as queue:
        update = _next_streaming_update(queue)
        assert str(task.object_id) in update.get("taskViewsByTaskId", {})
        assert "userUpdate" in update


# Note: 403 (forbidden) requires two distinct user sessions. The anonymous-only
# test fixtures only support one user, so the 403 path is exercised via the
# unit test in streams_scope_test.py (which calls resolve_stream_scope directly
# with mismatched user references). Re-add an HTTP-level 403 test once
# multi-user fixtures land.
