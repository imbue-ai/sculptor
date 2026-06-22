"""
Test the API endpoints for the Sculptor application.

NOTE: Endpoints are not currently tested for cross-user authorization (preventing users from changing resources such as
     tasks or user profiles belonging to other users). This coverage is needed before any multi-user deployment.

"""

from pathlib import Path
from typing import Generator

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import sculptor.services.user_config.user_config as user_config_module
from sculptor.config.user_config import UserConfig
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import model_dump
from sculptor.foundation.pydantic_utils import model_update
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import ToolUseID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.terminal_agent_registry import registry as registry_module
from sculptor.services.user_config.user_config import get_privacy_settings_for_telemetry
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.web.app import _agent_config_for_request
from sculptor.web.auth import SESSION_TOKEN_HEADER_NAME
from sculptor.web.auth import UserSession
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import AgentTypeName
from sculptor.web.data_types import CreateAgentRequest
from sculptor.web.data_types import SendMessageRequest
from sculptor.web.data_types import SetModelRequest
from sculptor.web.data_types import StartTaskRequest

# Check session token enforcement on the telemetry endpoint.


def test_endpoints_return_403_when_session_token_required_but_not_set(
    client_with_session_token_required: TestClient,
) -> None:
    response = client_with_session_token_required.get("/api/v1/telemetry_info")
    assert response.status_code == 403


def test_endpoints_return_200_when_session_token_required_and_set(
    client_with_session_token_required: TestClient,
) -> None:
    response = client_with_session_token_required.get(
        "/api/v1/telemetry_info", headers={SESSION_TOKEN_HEADER_NAME: "test_token"}
    )
    assert response.status_code == 200


def test_endpoints_return_200_when_session_token_required_and_set_via_a_get_param(
    client_with_session_token_required: TestClient,
) -> None:
    response = client_with_session_token_required.get(f"/api/v1/telemetry_info?{SESSION_TOKEN_HEADER_NAME}=test_token")
    assert response.status_code == 200


def test_endpoints_return_200_when_session_token_required_and_set_via_a_cookie(
    client_with_session_token_required: TestClient,
) -> None:
    response = client_with_session_token_required.get(
        "/api/v1/telemetry_info", cookies={SESSION_TOKEN_HEADER_NAME: "test_token"}
    )
    assert response.status_code == 200


def test_endpoints_return_200_when_api_secret_key_not_required_and_not_set(client: TestClient) -> None:
    response = client.get("/api/v1/telemetry_info")
    assert response.status_code == 200


def test_health_endpoint_never_requires_a_token(client_with_session_token_required: TestClient) -> None:
    response = client_with_session_token_required.get("/api/v1/health")
    assert response.status_code == 200


def test_get_session_token_returns_204_and_sets_cookie_even_when_header_not_set(
    client_with_session_token_required: TestClient,
) -> None:
    response = client_with_session_token_required.get("/api/v1/session-token")
    assert response.status_code == 204
    assert "set-cookie" in response.headers
    assert response.headers["set-cookie"].startswith(SESSION_TOKEN_HEADER_NAME)
    assert response.headers["set-cookie"].endswith("; HttpOnly; Path=/; SameSite=strict")
    assert "test_token" in response.headers["set-cookie"]


# The remaining tests go below.


def _create_workspace(
    transaction: DataModelTransaction,
    services: CompleteServiceCollection,
    project: Project,
    description: str = "test workspace",
) -> Workspace:
    """Create an IN_PLACE workspace for testing."""
    return services.workspace_service.create_workspace(
        project=project,
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        source_branch=None,
        requested_branch_name=None,
        description=description,
        transaction=transaction,
    )


def _create_task_in_workspace(
    transaction: DataModelTransaction,
    user_session: UserSession,
    project: Project,
    services: CompleteServiceCollection,
    workspace: Workspace,
    agent_config: HelloAgentConfig | ClaudeCodeSDKAgentConfig | None = None,
) -> Task:
    """Create a task associated with a specific workspace."""
    task_id = TaskID()
    task = Task(
        object_id=task_id,
        user_reference=user_session.user_reference,
        organization_reference=user_session.organization_reference,
        project_id=project.object_id,
        input_data=AgentTaskInputsV2(
            agent_config=agent_config if agent_config is not None else HelloAgentConfig(),
            git_hash="doesn't matter",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=workspace.object_id),
    )
    services.task_service.create_task(task, transaction)
    return task


def _create_task_with_message_in_workspace(
    transaction: DataModelTransaction,
    user_session: UserSession,
    project: Project,
    services: CompleteServiceCollection,
    workspace: Workspace,
) -> Task:
    """Create a task with an initial message, associated with a workspace."""
    task = _create_task_in_workspace(transaction, user_session, project, services, workspace)
    services.task_service.create_message(
        ChatInputUserMessage(
            model_name=LLMModel.CLAUDE_4_SONNET,
            text="foo",
        ),
        task.object_id,
        transaction=transaction,
    )
    return task


def create_claude_task(
    transaction: DataModelTransaction,
    user_session: UserSession,
    project: Project,
    services: CompleteServiceCollection,
    workspace: Workspace,
) -> Task:
    task_id = TaskID()
    task = Task(
        object_id=task_id,
        user_reference=user_session.user_reference,
        organization_reference=user_session.organization_reference,
        project_id=project.object_id,
        input_data=AgentTaskInputsV2(
            agent_config=ClaudeCodeSDKAgentConfig(),
            git_hash="doesn't matter",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=workspace.object_id),
    )
    services.task_service.create_task(task, transaction)
    return task


def test_create_task_creates_task(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    _user_session = authenticate_anonymous(test_services, RequestID())
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks",
        json=model_dump(
            StartTaskRequest(
                prompt="foo",
                model=LLMModel.CLAUDE_4_SONNET,
            ),
            is_camel_case=True,
        ),
    )
    if response.status_code == 422:
        raise AssertionError(f"Validation failed: {response.json()}. ")
    assert response.status_code == 200
    workspace_id = response.json()["workspaceId"]
    response = client.get(f"/api/v1/workspaces/{workspace_id}/agents")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_task_returns_422_when_missing_required_attribute(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks",
        json={"requestId": str(RequestID())},
    )
    assert response.status_code == 422


def test_resolve_agent_by_prefix_unique(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    full_id = str(task.object_id)
    response = client.get(f"/api/v1/agents/by-prefix/{full_id[:10]}")
    assert response.status_code == 200
    assert response.json()["agentId"] == full_id


def test_resolve_agent_by_prefix_full_id(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    full_id = str(task.object_id)
    response = client.get(f"/api/v1/agents/by-prefix/{full_id}")
    assert response.status_code == 200
    assert response.json()["agentId"] == full_id


def test_resolve_agent_by_prefix_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/agents/by-prefix/tsk_doesnotexist")
    assert response.status_code == 404


def test_resolve_agent_by_prefix_ambiguous(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        _create_task_with_message_in_workspace(transaction, user_session, test_project, test_services, workspace)
        _create_task_with_message_in_workspace(transaction, user_session, test_project, test_services, workspace)
    response = client.get("/api/v1/agents/by-prefix/tsk_")
    assert response.status_code == 409


def test_delete_agent_removes_task(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task_1 = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
        task_2 = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/agents/{task_1.object_id}")
    assert response.status_code in (200, 204)
    response = client.get(f"/api/v1/workspaces/{workspace.object_id}/agents")
    assert response.status_code == 200
    data = response.json()
    for item in data:
        if item["id"] != str(task_2.object_id):
            assert item["isDeleted"]


def test_delete_agent_returns_404_if_agent_does_not_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/agents/{TaskID()}")
    assert response.status_code == 404


def test_delete_agent_returns_422_if_id_is_invalid(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/agents/onetwo")
    assert response.status_code == 422


def test_send_message_saves_message(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    with test_services.task_service.subscribe_to_all_tasks_for_user(
        user_reference=user_session.user_reference
    ) as queue:
        message_container = queue.get(timeout=2)
        original_message_ids = [
            message_and_task_id[0].message_id for message_and_task_id in message_container.messages
        ]
        original_message_count = len(message_container.messages)
        # Aside from the first message saved above, various system messages can be present, too.
        assert original_message_count > 0
        assert all([message_and_task_id[1] == task.object_id for message_and_task_id in message_container.messages])
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/messages",
        json=model_dump(
            SendMessageRequest(message="This is a test message.", model=LLMModel.CLAUDE_4_SONNET),
            is_camel_case=True,
        ),
    )
    if response.status_code == 422:
        raise AssertionError(f"Validation failed: {response.json()}. ")
    assert response.status_code in (200, 204)
    with test_services.task_service.subscribe_to_all_tasks_for_user(
        user_reference=user_session.user_reference
    ) as queue:
        message_container = queue.get(timeout=2)
        new_message_count = len(message_container.messages)
        assert new_message_count > original_message_count
        assert all([message_and_task_id[1] == task.object_id for message_and_task_id in message_container.messages])
        for message_and_task_id in message_container.messages:
            if message_and_task_id[0].message_id not in original_message_ids:
                assert isinstance(message_and_task_id[0], ChatInputUserMessage)
                break
        else:
            assert False, "New message not found in the message container."


def test_send_message_returns_404_if_agent_does_not_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{TaskID()}/messages",
        json=model_dump(
            SendMessageRequest(message="This is a test message.", model=LLMModel.CLAUDE_4_SONNET),
            is_camel_case=True,
        ),
    )
    if response.status_code == 422:
        raise AssertionError(f"Validation failed: {response.json()}. ")
    assert response.status_code == 404


def test_send_message_returns_422_when_agent_id_is_invalid(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{{onetwo}}/messages",
        json={"requestId": str(RequestID()), "message": "This is a test message"},
    )
    assert response.status_code == 422


def test_manual_422_responses_use_validation_error_list_format(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Manual HTTPException(422) responses must use the same list-of-dicts format
    as FastAPI's automatic Pydantic validation errors, so the generated client
    can parse them without crashing."""
    # Use an invalid workspace ID to trigger validate_workspace_id's manual 422
    response = client.get("/api/v1/workspaces/not-a-valid-id/agents")
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert isinstance(body["detail"], list), (
        f"Expected detail to be a list, got {type(body['detail'])}: {body['detail']}"
    )
    assert len(body["detail"]) >= 1
    error = body["detail"][0]
    assert "loc" in error
    assert "msg" in error
    assert "type" in error


def test_send_message_returns_422_when_missing_required_attribute(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/messages",
        json={"requestId": str(RequestID())},
    )
    assert response.status_code == 422


def test_send_message_returns_409_when_ask_user_question_pending(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Sending a message while AskUserQuestion is pending should return 409.

    When an agent has called AskUserQuestion and is waiting for a response,
    the UI shows the AUQ panel instead of the chat input. Allowing a message
    to be sent at this time (e.g. via the sculpt CLI) creates a confusing UI
    state. The endpoint must block the send and return 409 Conflict.
    """
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        # AUQ recognition is a Claude harness capability; HelloHarness reports False.
        task = _create_task_in_workspace(
            transaction,
            user_session,
            test_project,
            test_services,
            workspace,
            agent_config=ClaudeCodeSDKAgentConfig(),
        )

        # Simulate an AskUserQuestion tool call by persisting a
        # ResponseBlockAgentMessage that contains an AskUserQuestion ToolUseBlock.
        # This is how the state is reconstructed from the message history (e.g. on
        # page reload), and it's what convert_agent_messages_to_task_update uses to
        # detect a pending question.
        tool_use_id = ToolUseID("toolu_ask_user_question_1")
        test_services.task_service.create_message(
            message=ResponseBlockAgentMessage(
                role="assistant",
                assistant_message_id=AssistantMessageID("msg_ask_user_question_1"),
                content=(
                    ToolUseBlock(
                        id=tool_use_id,
                        name="AskUserQuestion",
                        input={
                            "questions": [
                                {
                                    "question": "Which approach?",
                                    "header": "Approach",
                                    "options": [
                                        {"label": "A", "description": "Option A"},
                                        {"label": "B", "description": "Option B"},
                                    ],
                                    "multiSelect": False,
                                }
                            ]
                        },
                    ),
                ),
            ),
            task_id=task.object_id,
            transaction=transaction,
        )

    # Sending a normal message while AUQ is pending must be blocked.
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/messages",
        json=model_dump(
            SendMessageRequest(message="This message should be blocked.", model=LLMModel.CLAUDE_4_SONNET),
            is_camel_case=True,
        ),
    )
    assert response.status_code == 409


def test_send_message_rejects_enter_plan_mode_when_harness_lacks_backchannel(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Plan mode depends on the harness's interactive backchannel capability;
    rejecting the request honestly is better than silently ignoring the flag.
    HelloHarness advertises `supports_interactive_backchannel=False`, so the
    gate fires here even though `_create_task_with_message_in_workspace`
    defaults to a Hello task.
    """
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/messages",
        json=model_dump(
            SendMessageRequest(
                message="Enter plan mode.",
                model=LLMModel.CLAUDE_4_SONNET,
                enter_plan_mode=True,
            ),
            is_camel_case=True,
        ),
    )
    assert response.status_code == 400


def test_set_model_rejects_harness_without_model_selection(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """The set-model endpoint mirrors the frontend model-selection gate: a harness
    that advertises `supports_model_selection=False` (HelloHarness) must reject the
    request rather than dispatch a SetModelUserMessage it cannot honor."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/set_model",
        json=model_dump(SetModelRequest(provider="anthropic", model_id="claude-haiku-4-5"), is_camel_case=True),
    )
    assert response.status_code == 400, response.text


def test_set_model_rejects_claude_harness_without_a_backend_catalog(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Claude advertises `supports_model_selection=True` but switches per turn and
    sources no backend catalog. The out-of-band set-model endpoint must reject it
    rather than enqueue a SetModelUserMessage the Claude wrapper never resolves,
    which would hang the request waiting for a terminal outcome."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_in_workspace(
            transaction,
            user_session,
            test_project,
            test_services,
            workspace,
            agent_config=ClaudeCodeSDKAgentConfig(),
        )
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/set_model",
        json=model_dump(SetModelRequest(provider="anthropic", model_id="claude-haiku-4-5"), is_camel_case=True),
    )
    assert response.status_code == 400, response.text


def test_update_naming_pattern_performs_update(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    new_pattern = "feature/{slug}"
    response = client.put(
        f"/api/v1/projects/{test_project.object_id}/naming_pattern",
        json={"requestId": str(RequestID()), "namingPattern": new_pattern},
    )
    assert response.status_code == 200
    assert response.json() == new_pattern
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        project = transaction.get_project(test_project.object_id)
        assert project is not None
        assert project.naming_pattern == new_pattern


def test_update_naming_pattern_returns_404_for_missing_project(client: TestClient) -> None:
    nonexistent_project_id = ProjectID()
    response = client.put(
        f"/api/v1/projects/{nonexistent_project_id}/naming_pattern",
        json={"requestId": str(RequestID()), "namingPattern": "x/{slug}"},
    )
    assert response.status_code == 404


@pytest.mark.skip(reason="We need to resolve user project boostrapping first.")
def test_get_repo_info_returns_200(client: TestClient, test_project: Project) -> None:
    response = client.get(f"/api/v1/projects/{test_project.object_id}/repo_info")
    assert response.status_code == 200
    data = response.json()
    assert "repo_path" in data
    assert "current_branch" in data


def test_get_artifact_data_returns_data_if_they_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    artifact_data = DiffArtifact(uncommitted_diff="world").model_dump_json()
    test_services.task_service.set_artifact_file_data(task.object_id, ArtifactType.DIFF, artifact_data)
    response = client.get(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/artifacts/{ArtifactType.DIFF}",
    )
    assert response.status_code == 200
    data = response.json()
    validated_data = DiffArtifact.model_validate(data)
    expected = DiffArtifact.model_validate_json(artifact_data)
    assert validated_data == expected


def test_get_artifact_data_returns_404_if_artifact_does_not_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )
    response = client.get(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/artifacts/{ArtifactType.DIFF}",
    )
    assert response.status_code == 404


def test_get_artifact_data_returns_404_if_agent_does_not_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.get(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{TaskID()}/artifacts/{ArtifactType.DIFF}",
    )
    assert response.status_code == 404


def test_get_artifact_data_returns_422_if_agent_id_is_not_valid(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    _user_session = authenticate_anonymous(test_services, RequestID())
    fake_task_id = "tsk_01234567890123456789012345"
    with _user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.get(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{fake_task_id}/artifacts/{ArtifactType.DIFF}"
    )
    assert response.status_code == 404


# =====================
# Workspace auto-deletion and orphaned task protection tests
# =====================


def test_delete_agent_does_not_delete_workspace_when_other_agents_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Create 2 agents sharing a workspace. Delete one. Verify workspace still exists."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project, description="shared workspace")
        task_1 = _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)
        task_2 = _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)

    # Delete task_1
    response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/agents/{task_1.object_id}")
    assert response.status_code in (200, 204)

    # Verify workspace still exists
    with user_session.open_transaction(test_services) as transaction:
        remaining_workspace = transaction.get_workspace(workspace.object_id)
        assert remaining_workspace is not None, "Workspace should still exist when another task uses it"
        assert not remaining_workspace.is_deleted

    # Verify task_2 still exists
    with user_session.open_transaction(test_services) as transaction:
        remaining_task = test_services.task_service.get_task(task_2.object_id, transaction)
        assert remaining_task is not None
        assert not remaining_task.is_deleted


def test_delete_last_agent_preserves_workspace(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Create 1 agent in workspace. Delete it. Verify workspace still exists."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project, description="solo workspace")
        task = _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)

    # Delete the only agent
    response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}")
    assert response.status_code in (200, 204)

    # Verify workspace still exists (agents are managed independently from workspaces)
    with user_session.open_transaction(test_services) as transaction:
        remaining_workspace = transaction.get_workspace(workspace.object_id)
        assert remaining_workspace is not None, "Workspace should survive when its last agent is deleted"
        assert not remaining_workspace.is_deleted


def test_restore_agent_fails_when_workspace_deleted(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Agent in FAILED state, delete workspace directly, attempt restore. Verify HTTP 404."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project, description="restore test workspace")
        task = _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)

    # Set task to FAILED state
    with user_session.open_transaction(test_services) as transaction:
        fetched_task = test_services.task_service.get_task(task.object_id, transaction)
        assert fetched_task is not None
        updated_task = fetched_task.evolve(fetched_task.ref().outcome, TaskState.FAILED)
        # pyrefly: ignore [missing-attribute]
        transaction.upsert_task(updated_task)

    # Delete the workspace directly
    with user_session.open_transaction(test_services) as transaction:
        test_services.workspace_service.delete_workspace(workspace.object_id, transaction)

    # Attempt to restore — should fail with 404 because workspace is gone
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/restore",
    )
    assert response.status_code == 404


# =====================
# Mark read / unread tests
# =====================


def test_mark_read_sets_last_read_at(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)

    response = client.patch(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/mark-read",
    )
    assert response.status_code == 200

    with user_session.open_transaction(test_services) as transaction:
        updated_task = test_services.task_service.get_task(task.object_id, transaction)
        assert updated_task is not None
        assert updated_task.last_read_at is not None


def test_mark_read_returns_404_if_agent_does_not_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.patch(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{TaskID()}/mark-read",
    )
    assert response.status_code == 404


def test_mark_unread_clears_last_read_at(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)

    # First mark as read
    response = client.patch(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/mark-read",
    )
    assert response.status_code == 200

    # Then mark as unread
    response = client.patch(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{task.object_id}/mark-unread",
    )
    assert response.status_code == 200

    with user_session.open_transaction(test_services) as transaction:
        updated_task = test_services.task_service.get_task(task.object_id, transaction)
        assert updated_task is not None
        assert updated_task.last_read_at is None


def test_mark_unread_returns_404_if_agent_does_not_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
    response = client.patch(
        f"/api/v1/workspaces/{workspace.object_id}/agents/{TaskID()}/mark-unread",
    )
    assert response.status_code == 404


# --- Auto-send intro help message tests ---


def test_create_agent_sends_intro_message_for_first_agent(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """First-time users (no existing workspaces/agents) should get an auto-sent /sculptor:help message."""
    user_session = authenticate_anonymous(test_services, RequestID())

    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents",
        json=model_dump(CreateAgentRequest(model=LLMModel.CLAUDE_4_SONNET), is_camel_case=True),
    )
    assert response.status_code == 200
    agent_id = response.json()["id"]

    # Verify the intro message was persisted in the DB
    with user_session.open_transaction(test_services) as transaction:
        saved_messages = test_services.task_service.get_saved_messages_for_task(TaskID(agent_id), transaction)
    assert len(saved_messages) == 1
    intro_msg = saved_messages[0]
    assert isinstance(intro_msg, ChatInputUserMessage)
    assert "/sculptor:help" in intro_msg.text


def test_create_agent_does_not_send_intro_message_when_agents_exist(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Users with existing agents should not get an auto-sent intro message."""
    user_session = authenticate_anonymous(test_services, RequestID())

    # Create a workspace with an existing agent
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        _create_task_in_workspace(transaction, user_session, test_project, test_services, workspace)

    # Create a second agent in the same workspace
    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents",
        json=model_dump(CreateAgentRequest(model=LLMModel.CLAUDE_4_SONNET), is_camel_case=True),
    )
    assert response.status_code == 200
    agent_id = response.json()["id"]

    # No intro message should be in the DB for the new agent
    with user_session.open_transaction(test_services) as transaction:
        saved_messages = test_services.task_service.get_saved_messages_for_task(TaskID(agent_id), transaction)
    assert len(saved_messages) == 0


# Telemetry consent endpoints.


@pytest.fixture
def telemetry_test_config(tmp_path, monkeypatch) -> Generator[UserConfig, None, None]:
    """A logged-in user config with telemetry enabled, persisted to a tmp config path."""
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", tmp_path / "config.toml")
    config = UserConfig(
        user_email="alice@example.com",
        user_id="user_123",
        organization_id="org_123",
        instance_id="instance_123",
        is_privacy_policy_consented=True,
        is_telemetry_level_set=True,
        **get_privacy_settings_for_telemetry(True).model_dump(),
    )
    set_user_config_instance(config)
    yield config
    set_user_config_instance(None)


def test_set_telemetry_endpoint_disables_telemetry(client: TestClient, telemetry_test_config: UserConfig) -> None:
    response = client.post("/api/v1/config/telemetry", json={"enabled": False})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["isErrorReportingEnabled"] is False
    assert body["isProductAnalyticsEnabled"] is False
    assert body["isSessionRecordingEnabled"] is False
    # The flip is persisted on the singleton (and written to the tmp config file).
    assert user_config_module.get_user_config_instance().is_error_reporting_enabled is False
    assert user_config_module.get_config_path().exists()


def test_set_telemetry_endpoint_enables_telemetry(client: TestClient, telemetry_test_config: UserConfig) -> None:
    set_user_config_instance(
        model_update(telemetry_test_config, get_privacy_settings_for_telemetry(False).model_dump())
    )

    response = client.post("/api/v1/config/telemetry", json={"enabled": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["isErrorReportingEnabled"] is True
    assert body["isProductAnalyticsEnabled"] is True
    # Session recording stays off even when telemetry is enabled.
    assert body["isSessionRecordingEnabled"] is False


def test_put_user_config_rejects_telemetry_flag_change(client: TestClient, telemetry_test_config: UserConfig) -> None:
    response = client.put("/api/v1/config", json={"userConfig": {"isProductAnalyticsEnabled": False}})
    assert response.status_code == 400, response.text
    assert "/api/v1/config/telemetry" in response.json()["detail"]
    # The flag is unchanged.
    assert user_config_module.get_user_config_instance().is_product_analytics_enabled is True


def test_put_user_config_no_op_telemetry_flag_passes_through(
    client: TestClient, telemetry_test_config: UserConfig
) -> None:
    response = client.put(
        "/api/v1/config",
        json={"userConfig": {"isProductAnalyticsEnabled": True, "isAlwaysInterruptAndSend": True}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["isAlwaysInterruptAndSend"] is True


@pytest.fixture
def onboarding_test_config(tmp_path, monkeypatch) -> Generator[UserConfig, None, None]:
    """A fresh anonymous config, as it exists before the onboarding welcome step."""
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", tmp_path / "config.toml")
    config = user_config_module.get_default_user_config_instance()
    set_user_config_instance(config)
    yield config
    set_user_config_instance(None)


def test_skip_account_setup_keeps_anonymous_identity_and_records_choice(
    client: TestClient, onboarding_test_config: UserConfig
) -> None:
    response = client.post("/api/v1/config/skip_account", json={"isTelemetryEnabled": False})
    assert response.status_code == 200, response.text
    saved = user_config_module.get_user_config_instance()
    assert saved.user_email == ""
    assert saved.is_privacy_policy_consented is True
    assert saved.is_telemetry_level_set is True
    assert saved.is_error_reporting_enabled is False
    assert saved.is_product_analytics_enabled is False
    # The response carries the updated config for the FE handshake.
    assert response.json()["userConfig"]["isProductAnalyticsEnabled"] is False


def test_skip_account_setup_defaults_to_telemetry_enabled(
    client: TestClient, onboarding_test_config: UserConfig
) -> None:
    response = client.post("/api/v1/config/skip_account", json={})
    assert response.status_code == 200, response.text
    saved = user_config_module.get_user_config_instance()
    assert saved.is_error_reporting_enabled is True
    assert saved.is_product_analytics_enabled is True


def test_save_user_email_applies_telemetry_choice(client: TestClient, onboarding_test_config: UserConfig) -> None:
    response = client.post(
        "/api/v1/config/email",
        json={"userEmail": "bob@example.com", "fullName": "Bob", "isTelemetryEnabled": False},
    )
    assert response.status_code == 200, response.text
    saved = user_config_module.get_user_config_instance()
    assert saved.user_email == "bob@example.com"
    assert saved.is_privacy_policy_consented is True
    assert saved.is_error_reporting_enabled is False
    assert saved.is_product_analytics_enabled is False


def test_complete_onboarding_allows_empty_email_after_skip(
    client: TestClient, onboarding_test_config: UserConfig
) -> None:
    skip_response = client.post("/api/v1/config/skip_account", json={"isTelemetryEnabled": True})
    assert skip_response.status_code == 200, skip_response.text

    response = client.post("/api/v1/config/complete")
    assert response.status_code == 200, response.text


def test_complete_onboarding_rejects_empty_email_without_welcome_step(
    client: TestClient, onboarding_test_config: UserConfig
) -> None:
    response = client.post("/api/v1/config/complete")
    assert response.status_code == 400, response.text
    assert "Welcome step" in response.json()["detail"]


# Agent-type creation path (terminal agents).


def test_agent_config_for_request_resolves_each_type() -> None:
    # Agent type comes only from the creation request.
    assert isinstance(_agent_config_for_request(AgentTypeName.TERMINAL, None), TerminalAgentConfig)
    with pytest.raises(HTTPException) as exc_info:
        _agent_config_for_request(AgentTypeName.REGISTERED, "some-registration")
    assert exc_info.value.status_code == 422
    assert isinstance(_agent_config_for_request(AgentTypeName.CLAUDE, None), ClaudeCodeSDKAgentConfig)
    assert isinstance(_agent_config_for_request(AgentTypeName.PI, None), PiAgentConfig)


def test_start_task_resolves_agent_type(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """Prompt-ful creation honors a chat agent_type and rejects terminal types."""
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks",
        json=model_dump(
            StartTaskRequest(
                prompt="hello pi",
                model=LLMModel.CLAUDE_4_SONNET,
                agent_type=AgentTypeName.PI,
            ),
            is_camel_case=True,
        ),
    )
    assert response.status_code == 200, response.text
    task_id = TaskID(response.json()["id"])
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(task_id, transaction)
    assert task is not None
    assert isinstance(task.input_data, AgentTaskInputsV2)
    assert isinstance(task.input_data.agent_config, PiAgentConfig)

    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks",
        json=model_dump(
            StartTaskRequest(
                prompt="hello terminal",
                model=LLMModel.CLAUDE_4_SONNET,
                agent_type=AgentTypeName.TERMINAL,
            ),
            is_camel_case=True,
        ),
    )
    assert response.status_code == 422


def _post_agent(client: TestClient, workspace: Workspace, body: dict) -> httpx.Response:
    return client.post(f"/api/v1/workspaces/{workspace.object_id}/agents", json=body)


def test_create_terminal_agent_stamps_terminal_config_and_names_terminal_n(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    first = _post_agent(client, workspace, {"agentType": "terminal"})
    assert first.status_code == 200, first.text
    assert first.json()["title"] == "Terminal 1"
    first_task_id = TaskID(first.json()["id"])

    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(first_task_id, transaction)
    assert task is not None
    assert isinstance(task.input_data, AgentTaskInputsV2)
    assert task.input_data.agent_config.object_type == "TerminalAgentConfig"

    # Numbering is independent per prefix: a chat agent is "Claude 1".
    chat = _post_agent(client, workspace, {})
    assert chat.status_code == 200, chat.text
    assert chat.json()["title"] == "Claude 1"

    second = _post_agent(client, workspace, {"agentType": "terminal"})
    assert second.status_code == 200, second.text
    assert second.json()["title"] == "Terminal 2"

    # Lowest-available reuse: deleting "Terminal 1" frees its number.
    delete_response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/agents/{first_task_id}")
    assert delete_response.status_code in (200, 204)
    third = _post_agent(client, workspace, {"agentType": "terminal"})
    assert third.status_code == 200, third.text
    assert third.json()["title"] == "Terminal 1"


@pytest.fixture
def isolated_user_config(tmp_path, monkeypatch) -> Generator[None, None, None]:
    """Isolate the on-disk config path and reset the config singleton after.

    The most-recently-used harness tests set a real config instance (so the
    server records/reads it) and must not write the developer's actual config
    or leak the singleton into other tests.
    """
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", tmp_path / "config.toml")
    yield
    set_user_config_instance(None)


def _set_user_config_with(**fields: object) -> None:
    set_user_config_instance(model_update(user_config_module.get_default_user_config_instance(), fields))


def _agent_config_for_created(response: httpx.Response, test_services: CompleteServiceCollection) -> object:
    task_id = TaskID(response.json()["id"])
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(task_id, transaction)
    assert task is not None
    assert isinstance(task.input_data, AgentTaskInputsV2)
    return task.input_data.agent_config


def test_create_agent_without_type_uses_mru_harness(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    isolated_user_config: None,
) -> None:
    """A prompt-less create with no agent_type resolves the user's stored MRU."""
    _set_user_config_with(last_used_agent_type="terminal")
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = _post_agent(client, workspace, {})
    assert response.status_code == 200, response.text
    assert isinstance(_agent_config_for_created(response, test_services), TerminalAgentConfig)
    assert response.json()["title"] == "Terminal 1"


def test_create_agent_records_explicit_type_as_mru(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    isolated_user_config: None,
) -> None:
    """An explicit agent_type is persisted as the new most-recently-used harness."""
    _set_user_config_with()  # no MRU yet
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    assert _post_agent(client, workspace, {"agentType": "terminal"}).status_code == 200
    assert user_config_module.get_user_config_instance().last_used_agent_type == "terminal"


def test_create_agent_without_type_defaults_to_claude_when_mru_unset(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    isolated_user_config: None,
) -> None:
    _set_user_config_with()  # no MRU
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = _post_agent(client, workspace, {})
    assert response.status_code == 200, response.text
    assert isinstance(_agent_config_for_created(response, test_services), ClaudeCodeSDKAgentConfig)


def test_create_agent_pi_mru_falls_back_to_claude_when_pi_disabled(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    isolated_user_config: None,
) -> None:
    """A stored Pi harness is unusable once the pi agent is disabled."""
    _set_user_config_with(last_used_agent_type="pi", enable_pi_agent=False)
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = _post_agent(client, workspace, {})
    assert response.status_code == 200, response.text
    assert isinstance(_agent_config_for_created(response, test_services), ClaudeCodeSDKAgentConfig)


def test_start_task_terminal_mru_falls_back_to_claude_for_prompt(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    isolated_user_config: None,
) -> None:
    """A prompt-ful create with a terminal MRU uses Claude rather than 422ing."""
    _set_user_config_with(last_used_agent_type="terminal")
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks",
        json=model_dump(
            StartTaskRequest(prompt="hello", model=LLMModel.CLAUDE_4_SONNET),
            is_camel_case=True,
        ),
    )
    assert response.status_code == 200, response.text
    assert isinstance(_agent_config_for_created(response, test_services), ClaudeCodeSDKAgentConfig)


def test_create_terminal_agent_with_prompt_is_rejected(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = _post_agent(client, workspace, {"agentType": "terminal", "prompt": "hi"})
    assert response.status_code == 422
    response = _post_agent(client, workspace, {"agentType": "registered", "prompt": "hi"})
    assert response.status_code == 422


def test_first_terminal_agent_gets_no_intro_message(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = _post_agent(client, workspace, {"agentType": "terminal"})
    assert response.status_code == 200, response.text
    task_id = TaskID(response.json()["id"])

    with user_session.open_transaction(test_services) as transaction:
        messages = test_services.task_service.get_saved_messages_for_task(task_id, transaction)
    assert not any(isinstance(m, ChatInputUserMessage) for m in messages)


def test_first_claude_agent_still_gets_intro_message(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = _post_agent(client, workspace, {})
    assert response.status_code == 200, response.text
    task_id = TaskID(response.json()["id"])

    with user_session.open_transaction(test_services) as transaction:
        messages = test_services.task_service.get_saved_messages_for_task(task_id, transaction)
    assert any(isinstance(m, ChatInputUserMessage) for m in messages)


# Terminal-agent registrations.


@pytest.fixture
def registrations_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(registry_module, "get_sculptor_folder", lambda: tmp_path)
    directory = tmp_path / "terminal_agents"
    directory.mkdir()
    return directory


def test_list_terminal_agent_registrations_rereads_per_request(client: TestClient, registrations_dir: Path) -> None:
    response = client.get("/api/v1/terminal-agent-registrations")
    assert response.status_code == 200
    assert response.json()["registrations"] == []

    # A file dropped between two calls appears without a restart (no caching).
    (registrations_dir / "claude-code.toml").write_text('display_name = "Claude Code"\nlaunch_command = "claude"\n')
    response = client.get("/api/v1/terminal-agent-registrations")
    assert response.status_code == 200
    listed = response.json()["registrations"]
    assert [r["registrationId"] for r in listed] == ["claude-code"]
    assert listed[0]["displayName"] == "Claude Code"


def test_list_terminal_agent_registrations_skips_bad_files(client: TestClient, registrations_dir: Path) -> None:
    (registrations_dir / "broken.toml").write_text("not [valid toml")
    (registrations_dir / "good.toml").write_text('display_name = "Good"\nlaunch_command = "good"\n')

    response = client.get("/api/v1/terminal-agent-registrations")

    assert response.status_code == 200
    assert [r["registrationId"] for r in response.json()["registrations"]] == ["good"]


def test_create_registered_agent_stamps_resolved_config_and_names_from_display_name(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    registrations_dir: Path,
) -> None:
    (registrations_dir / "claude-code.toml").write_text(
        """\
display_name = "Claude Code"
launch_command = "claude"
resume_command_template = "claude --resume {session_id}"
accepts_automated_prompts = true
"""
    )
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = _post_agent(client, workspace, {"agentType": "registered", "registrationId": "claude-code"})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Claude Code 1"

    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(TaskID(response.json()["id"]), transaction)
    assert task is not None
    assert isinstance(task.input_data, AgentTaskInputsV2)
    config = task.input_data.agent_config
    assert isinstance(config, RegisteredTerminalAgentConfig)
    assert config.registration_id == "claude-code"
    assert config.display_name == "Claude Code"
    assert config.launch_command == "claude"
    assert config.resume_command_template == "claude --resume {session_id}"
    assert config.accepts_automated_prompts is True


def test_create_registered_agent_with_unknown_or_deleted_registration_fails(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    registrations_dir: Path,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    assert _post_agent(client, workspace, {"agentType": "registered", "registrationId": "nope"}).status_code == 422

    # Menu-raced deletion: the file existed when the menu listed it but is
    # gone by creation time.
    path = registrations_dir / "fleeting.toml"
    path.write_text('display_name = "Fleeting"\nlaunch_command = "x"\n')
    assert client.get("/api/v1/terminal-agent-registrations").json()["registrations"]
    path.unlink()
    response = _post_agent(client, workspace, {"agentType": "registered", "registrationId": "fleeting"})
    assert response.status_code == 422
    assert "fleeting" in response.json()["detail"]
