"""Tests for the create-time model contract.

A create names its model on exactly one harness's terms: `model` for Claude's
static list, `backend_model` for a backend-sourced catalog (pi). A pi prompt
requires a `backend_model` whose provider is authenticated at create time, and
the accepted selection is seeded as the task's `current_model`. A promptless
create must not carry a `backend_model` at all — post-start selection owns
that case.
"""

from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import TaskID
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import model_dump
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.state.messages import LLMModel
from sculptor.state.messages import ModelOption
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import AgentTypeName
from sculptor.web.data_types import CreateAgentRequest
from sculptor.web.data_types import StartTaskRequest

_OPUS = ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="Claude Opus 4.8")


def _post_task(client: TestClient, project: Project, request: StartTaskRequest) -> httpx.Response:
    return client.post(
        f"/api/v1/projects/{project.object_id}/tasks",
        json=model_dump(request, is_camel_case=True),
    )


def _create_workspace(
    transaction: DataModelTransaction,
    services: CompleteServiceCollection,
    project: Project,
) -> Workspace:
    return services.workspace_service.create_workspace(
        project=project,
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        source_branch=None,
        requested_branch_name=None,
        description="test workspace",
        transaction=transaction,
    )


def test_pi_prompt_with_authenticated_backend_model_seeds_current_model(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    with patch("sculptor.web.app.compute_authenticated_provider_ids", return_value={"anthropic"}):
        response = _post_task(
            client,
            test_project,
            StartTaskRequest(prompt="hello pi", backend_model=_OPUS, agent_type=AgentTypeName.PI),
        )
    assert response.status_code == 200, response.text

    task_id = TaskID(response.json()["id"])
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(task_id, transaction)
    assert task is not None
    assert isinstance(task.current_state, AgentTaskStateV2)
    # The validated selection is the task's current model from birth, so the
    # wrapper's start-time adoption runs the queued prompt under it.
    assert task.current_state.current_model == _OPUS
    assert isinstance(task.input_data, AgentTaskInputsV2)
    assert task.input_data.default_model is None


def test_pi_prompt_without_backend_model_is_rejected(client: TestClient, test_project: Project) -> None:
    response = _post_task(
        client,
        test_project,
        StartTaskRequest(prompt="hello pi", agent_type=AgentTypeName.PI),
    )
    assert response.status_code == 422
    assert "backend_model" in response.text


def test_pi_prompt_with_unauthenticated_provider_is_rejected(client: TestClient, test_project: Project) -> None:
    with patch("sculptor.web.app.compute_authenticated_provider_ids", return_value=set()):
        response = _post_task(
            client,
            test_project,
            StartTaskRequest(prompt="hello pi", backend_model=_OPUS, agent_type=AgentTypeName.PI),
        )
    assert response.status_code == 422
    assert "not authenticated" in response.text


def test_model_and_backend_model_together_are_rejected(client: TestClient, test_project: Project) -> None:
    with patch("sculptor.web.app.compute_authenticated_provider_ids", return_value={"anthropic"}):
        response = _post_task(
            client,
            test_project,
            StartTaskRequest(
                prompt="hello",
                model=LLMModel.CLAUDE_4_SONNET,
                backend_model=_OPUS,
                agent_type=AgentTypeName.PI,
            ),
        )
    assert response.status_code == 422
    assert "mutually exclusive" in response.text


def test_promptless_backend_model_is_rejected(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    """A promptless create has no turn to run the selection under — post-start
    selection owns that case — so a backend_model riding one is rejected
    rather than silently dropped."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)

    response = client.post(
        f"/api/v1/workspaces/{workspace.object_id}/agents",
        json=model_dump(
            CreateAgentRequest(agent_type=AgentTypeName.PI, backend_model=_OPUS),
            is_camel_case=True,
        ),
    )
    assert response.status_code == 422
    assert "backend_model requires a prompt" in response.text


def test_claude_prompt_without_model_is_rejected(client: TestClient, test_project: Project) -> None:
    response = _post_task(
        client,
        test_project,
        StartTaskRequest(prompt="hello claude", agent_type=AgentTypeName.CLAUDE),
    )
    assert response.status_code == 422
    assert "Model is required when providing a prompt" in response.text


def test_claude_prompt_with_model_is_unchanged(
    client: TestClient, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    response = _post_task(
        client,
        test_project,
        StartTaskRequest(prompt="hello claude", model=LLMModel.CLAUDE_4_SONNET, agent_type=AgentTypeName.CLAUDE),
    )
    assert response.status_code == 200, response.text

    task_id = TaskID(response.json()["id"])
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(task_id, transaction)
    assert task is not None
    assert isinstance(task.current_state, AgentTaskStateV2)
    # Claude's model rides `default_model`/`model_name`, never the backend
    # catalog's `current_model`.
    assert task.current_state.current_model is None
    assert isinstance(task.input_data, AgentTaskInputsV2)
    assert task.input_data.default_model == LLMModel.CLAUDE_4_SONNET
