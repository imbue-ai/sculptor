"""
Test the API endpoints for the Sculptor application.

TODO: Test that all relevant endpoints prevent users from changing resources (tasks, user profiles, ...) belonging to other users.
     (Probably when we actually start working on multi-user deployments.)

"""

import hashlib
import os
from pathlib import Path

import pytest

import imbue_core.sculptor.telemetry as telemetry_module
import sculptor.config.user_config as user_config_module
from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.pydantic_serialization import model_dump
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.telemetry import TelemetryInfo
from imbue_core.sculptor.telemetry import init_posthog
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from imbue_core.sculptor.user_config import UserConfig
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import ArtifactType
from sculptor.interfaces.agents.v1.agent import DiffArtifact
from sculptor.interfaces.agents.v1.agent import HelloAgentConfig
from sculptor.interfaces.environments.v1.base import LocalDockerImageConfig
from sculptor.interfaces.environments.v1.base import LocalImageConfig
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import get_deterministic_typeid_suffix
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.web.auth import APP_SECRET_HEADER_NAME
from sculptor.web.auth import UserSession
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import SendMessageRequest
from sculptor.web.data_types import StartTaskRequest
from sculptor.web.data_types import UserInfo


def setup_telemetry_with_consent_level(consent_level: ConsentLevel) -> None:
    """Set up telemetry with specified consent level for testing."""
    user_email = "test@imbue.com"
    user_git_username = "test"
    user_reference = UserReference(get_deterministic_typeid_suffix(user_email))

    is_error_reporting_enabled = (
        consent_level == ConsentLevel.ERROR_REPORTING
        or consent_level == ConsentLevel.PRODUCT_ANALYTICS
        or consent_level == ConsentLevel.LLM_LOGS
        or consent_level == ConsentLevel.SESSION_RECORDING
    )
    is_product_analytics_enabled = (
        consent_level == ConsentLevel.PRODUCT_ANALYTICS
        or consent_level == ConsentLevel.LLM_LOGS
        or consent_level == ConsentLevel.SESSION_RECORDING
    )
    is_llm_logs_enabled = consent_level == ConsentLevel.LLM_LOGS or consent_level == ConsentLevel.SESSION_RECORDING
    is_session_recording_enabled = consent_level == ConsentLevel.SESSION_RECORDING

    user_config = UserConfig(
        user_email=user_email,
        user_git_username=user_git_username,
        user_id=str(user_reference),
        anonymous_access_token=hashlib.md5(os.urandom(64)).hexdigest(),
        organization_id=str(OrganizationReference(get_deterministic_typeid_suffix(str(user_reference)))),
        instance_id=hashlib.md5(os.urandom(64)).hexdigest(),
        is_error_reporting_enabled=is_error_reporting_enabled,
        is_product_analytics_enabled=is_product_analytics_enabled,
        is_llm_logs_enabled=is_llm_logs_enabled,
        is_session_recording_enabled=is_session_recording_enabled,
        is_repo_backup_enabled=True,
        is_suggestion_beta_feature_on=True,
    )

    user_config_module._CONFIG_INSTANCE = user_config

    telemetry_info = TelemetryInfo(
        user_config=user_config,
        sculptor_version="",
        sculptor_git_sha="",
        posthog_token="",
        posthog_api_host="",
        sentry_dsn="",
    )

    init_posthog(telemetry_info)


def reset_telemetry() -> None:
    """Reset the global telemetry state for testing."""

    telemetry_module._POSTHOG_USER_INSTANCE = None


# Check app secret enforcement on the root endpoint.


def test_get_root_returns_403_when_api_secret_key_required_but_not_set(client_with_app_secret_required) -> None:
    response = client_with_app_secret_required.get("/api/v1/version")
    assert response.status_code == 403


def test_get_root_returns_200_when_api_secret_key_required_and_set(client_with_app_secret_required) -> None:
    response = client_with_app_secret_required.get("/api/v1/version", headers={APP_SECRET_HEADER_NAME: "test_secret"})
    assert response.status_code == 200


def test_get_root_returns_200_when_api_secret_key_not_required_and_not_set(client) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200


# Check auth setup on the /auth/me endpoint.
def test_get_me_returns_200_when_authorized_via_header(client_with_auth, test_auth_headers) -> None:
    response = client_with_auth.get("/api/v1/auth/me", headers=test_auth_headers)
    assert response.status_code == 200
    UserInfo.model_validate(response.json())  #


def test_get_me_returns_200_when_authorized_via_get_param(client_with_auth, test_auth_headers) -> None:
    jwt = test_auth_headers["Authorization"].split(" ")[1]
    response = client_with_auth.get(f"/api/v1/auth/me?jwt={jwt}")
    assert response.status_code == 200


def test_get_me_returns_401_when_not_authorized(client_with_auth) -> None:
    response = client_with_auth.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_get_me_returns_401_when_token_is_invalid(client_with_auth) -> None:
    jwt = "invalid"
    response = client_with_auth.get(f"/api/v1/auth/me?jwt={jwt}")
    assert response.status_code == 401


# The remaining tests go below.


def create_saved_agent_message_and_task(
    transaction: DataModelTransaction, user_session: UserSession, project: Project, services: CompleteServiceCollection
) -> Task:
    task_id = TaskID()
    task = Task(
        object_id=task_id,
        user_reference=user_session.user_reference,
        organization_reference=user_session.organization_reference,
        project_id=project.object_id,
        parent_task_id=None,
        input_data=AgentTaskInputsV1(
            image_config=LocalDockerImageConfig(dockerfile_path="who cares"),
            agent_config=HelloAgentConfig(),
            git_hash="doesn't matter",
            initial_branch="also doesn't matter",
            is_git_state_clean=True,
        ),
    )
    services.task_service.create_task(task, transaction)
    services.task_service.create_message(
        ChatInputUserMessage(
            model_name=LLMModel.CLAUDE_4_SONNET,
            text="foo",
        ),
        task_id,
        transaction=transaction,
    )
    return task


def create_hello_agent_saved_agent_message_and_task(
    transaction: DataModelTransaction,
    user_session: UserSession,
    project: Project,
    services: CompleteServiceCollection,
    code_directory: Path,
) -> Task:
    task = Task(
        object_id=TaskID(),
        user_reference=user_session.user_reference,
        organization_reference=user_session.organization_reference,
        project_id=project.object_id,
        parent_task_id=None,
        input_data=AgentTaskInputsV1(
            agent_config=HelloAgentConfig(),
            image_config=LocalImageConfig(code_directory=code_directory),
            available_secrets=None,
            git_hash="HEAD",
            initial_branch="main",
            is_git_state_clean=False,
        ),
    )
    services.task_service.create_task(task, transaction)
    services.task_service.create_message(
        ChatInputUserMessage(text="foo", message_id=AgentMessageID(), model_name=LLMModel.CLAUDE_4_SONNET),
        task.object_id,
        transaction,
    )
    return task


def test_create_task_creates_task(client, test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks",
        json=model_dump(
            StartTaskRequest(
                prompt="foo",
                source_branch="main",
                model=LLMModel.CLAUDE_4_SONNET,
            ),
            is_camel_case=True,
        ),
    )
    if response.status_code == 422:
        raise AssertionError(f"Validation failed: {response.json()}. ")
    assert response.status_code == 200
    response = client.get(f"/api/v1/projects/{test_project.object_id}/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_task_returns_422_when_missing_required_attribute(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks",
        json={"requestId": str(RequestID())},
    )
    assert response.status_code == 422


def test_delete_task_removes_task(client, test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task_1 = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
        task_2 = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
    response = client.delete(f"/api/v1/projects/{test_project.object_id}/tasks/{task_1.object_id}")
    assert response.status_code in (200, 204)
    response = client.get(f"/api/v1/projects/{test_project.object_id}/tasks")
    assert response.status_code == 200
    data = response.json()
    for item in data:
        if item["id"] != str(task_2.object_id):
            assert item["isDeleted"]


def test_delete_task_return_404_if_task_does_not_exist(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    response = client.delete(f"/api/v1/projects/{test_project.object_id}/tasks/{TaskID()}")
    assert response.status_code == 404


def test_delete_task_returns_422_if_id_is_invalid(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    response = client.delete(f"/api/v1/projects/{test_project.object_id}/tasks/onetwo")
    assert response.status_code == 422


def test_send_message_saves_message(client, test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    # get the projectID
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
    with test_services.task_service.subscribe_to_complete_tasks_for_user(
        user_reference=user_session.user_reference, project_id=test_project.object_id
    ) as queue:
        message_container = queue.get(timeout=2)
        assert (
            len([message_and_task_id[1] == task.object_id for message_and_task_id in message_container.messages]) == 2
        )
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/messages",
        json=model_dump(
            SendMessageRequest(message="This is a test message.", model=LLMModel.CLAUDE_4_SONNET),
            is_camel_case=True,
        ),
    )
    if response.status_code == 422:
        raise AssertionError(f"Validation failed: {response.json()}. ")
    assert response.status_code in (200, 204)
    with test_services.task_service.subscribe_to_complete_tasks_for_user(
        user_reference=user_session.user_reference, project_id=test_project.object_id
    ) as queue:
        message_container = queue.get(timeout=2)
        assert (
            len([message_and_task_id[1] == task.object_id for message_and_task_id in message_container.messages]) == 3
        )


def test_send_message_returns_404_if_task_does_not_exist(client, test_project: Project) -> None:
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks/{TaskID()}/messages",
        json=model_dump(
            SendMessageRequest(message="This is a test message.", model=LLMModel.CLAUDE_4_SONNET),
            is_camel_case=True,
        ),
    )
    # FIXME: more generically apply this for easier debugging
    if response.status_code == 422:
        raise AssertionError(f"Validation failed: {response.json()}. ")
    assert response.status_code == 404


def test_send_message_returns_422_when_task_id_is_invalid(client, test_project: Project) -> None:
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks/{{onetwo}}/messages",
        json={"requestId": str(RequestID()), "message": "This is a test message"},
    )
    assert response.status_code == 422


def test_send_message_returns_422_when_missing_required_attribute(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
    response = client.post(
        f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/messages",
        json={"requestId": str(RequestID())},
    )
    assert response.status_code == 422


# TODO: Migrate this to a mock/test posthog instance.
def test_create_fix_returns_200(
    client_with_auth, test_auth_headers, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    setup_telemetry_with_consent_level(ConsentLevel.LLM_LOGS)

    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)

    response = client_with_auth.post(
        f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/fix",
        headers=test_auth_headers,
        json={
            "description": "Race condition in deposit method: multiple threads can read the same balance value.",
        },
    )
    assert response.status_code == 200


def test_create_fix_returns_422_when_missing_required_attribute(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)

    response = client.post(f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/fix", json={})
    assert response.status_code == 422


def test_update_default_system_prompt_performs_update(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    new_prompt = "This is a new default system prompt."
    response = client.put(
        f"/api/v1/projects/{test_project.object_id}/default_system_prompt",
        json={"requestId": str(RequestID()), "defaultSystemPrompt": new_prompt},
    )
    assert response.status_code == 200
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        project = transaction.get_project(test_project.object_id)
        assert project.default_system_prompt == new_prompt


def test_archive_task_archives_and_unarchives_task(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
    response = client.patch(
        f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/archive",
        json={"requestId": str(RequestID()), "isArchived": True},
    )
    assert response.status_code in (200, 204)
    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(task.object_id, transaction)
        assert task is not None
        assert task.is_archived is True
    response = client.patch(
        f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/archive",
        json={"requestId": str(RequestID()), "isArchived": False},
    )
    assert response.status_code in (200, 204)
    with user_session.open_transaction(test_services) as transaction:
        task = test_services.task_service.get_task(task.object_id, transaction)
        assert task is not None
        assert task.is_archived is False


def test_archive_task_returns_422_if_task_id_is_invalid(client, test_project: Project) -> None:
    response = client.patch(
        f"/api/v1/projects/{test_project.object_id}/tasks/abc/archive",
        json={"requestId": str(RequestID()), "isArchived": True},
    )
    assert response.status_code == 422


def test_archive_task_returns_404_if_task_does_not_exist(client, test_project: Project) -> None:
    response = client.patch(
        f"/api/v1/projects/{test_project.object_id}/tasks/{TaskID()}/archive",
        json={"requestId": str(RequestID()), "isArchived": True},
    )
    assert response.status_code == 404


def test_archive_task_returns_422_when_missing_required_attribute(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
    response = client.patch(f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/archive", json={})
    assert response.status_code == 422


@pytest.mark.skip(reason="We need to resolve user project boostrapping first.")
def test_get_repo_info_returns_200(client, test_project: Project) -> None:
    response = client.get(f"/api/v1/projects/{test_project.object_id}/repo_info")
    assert response.status_code == 200
    data = response.json()
    assert "repo_path" in data
    assert "current_branch" in data


def test_get_artifact_data_returns_data_if_they_exist(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
    artifact_data = DiffArtifact(
        committed_diff="hello", uncommitted_diff="world", complete_diff="hello world"
    ).model_dump_json()
    test_services.task_service.set_artifact_file_data(task.object_id, ArtifactType.DIFF, artifact_data)
    response = client.get(
        f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/artifacts/{ArtifactType.DIFF}",
    )
    assert response.status_code == 200
    data = response.json()
    validated_data = DiffArtifact.model_validate(data)
    expected = DiffArtifact.model_validate_json(artifact_data)
    assert validated_data == expected


def test_get_artifact_data_returns_404_if_artifact_does_not_exist(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)
    response = client.get(
        f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/artifacts/{ArtifactType.DIFF}",
    )
    assert response.status_code == 404


def test_get_artifact_data_returns_404_if_task_does_not_exist(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    response = client.get(
        f"/api/v1/projects/{test_project.object_id}/tasks/{TaskID()}/artifacts/{ArtifactType.DIFF}",
    )
    assert response.status_code == 404


def test_get_artifact_data_returns_422_if_task_id_is_not_valid(
    client, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    response = client.get(f"/api/v1/projects/{test_project.object_id}/tasks/abc/artifacts/{ArtifactType.DIFF}")
    assert response.status_code == 422
