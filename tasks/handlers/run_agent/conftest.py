import tempfile
from pathlib import Path
from typing import Generator
from typing import cast

import pytest

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.sculptor.state.messages import Message
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import HelloAgentConfig
from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalImageConfig
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.anthropic_credentials_service.default_implementation import DefaultAnthropicCredentialsService
from sculptor.services.configuration_broadcast_service.default_implementation import (
    DefaultConfigurationBroadcastService,
)
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.environment_service.api import EnvironmentService
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.local_sync_service.default_implementation import DefaultLocalSyncService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.secrets_service.api import SecretsService
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.threaded_implementation import LocalThreadTaskService


@pytest.fixture
def environment_config() -> LocalEnvironmentConfig:
    return LocalEnvironmentConfig()


@pytest.fixture
def project() -> Project:
    return Project(object_id=ProjectID(), name="Test Project", organization_reference=OrganizationReference("org_123"))


@pytest.fixture
def local_task(project: Project, environment_config: LocalEnvironmentConfig, tmp_path: Path) -> Task:
    return Task(
        object_id=TaskID(),
        organization_reference=project.organization_reference,
        user_reference=UserReference("usr_123"),
        project_id=project.object_id,
        input_data=AgentTaskInputsV1(
            agent_config=HelloAgentConfig(),
            image_config=LocalImageConfig(code_directory=tmp_path),
            environment_config=environment_config,
            git_hash="initialhash",
            initial_branch="main",
            is_git_state_clean=False,
        ),
        parent_task_id=None,
    )


@pytest.fixture
def test_settings_with_checks(test_settings: SculptorSettings) -> SculptorSettings:
    return test_settings.model_copy(update={"IS_CHECKS_ENABLED": True, "DOCKER_PROVIDER_ENABLED": False})


@pytest.fixture
def services(
    test_settings_with_checks: SculptorSettings,
    test_secrets_service: SecretsService,
    test_data_model_service: DataModelService,
    test_git_repo_service: GitRepoService,
    test_environment_service: EnvironmentService,
    test_local_sync_service: DefaultLocalSyncService,
    test_project_service: ProjectService,
    local_task: Task,
    project: Project,
) -> Generator[ServiceCollectionForTask, None, None]:
    task_service = LocalThreadTaskService(
        settings=test_settings_with_checks,
        secrets_service=test_secrets_service,
        data_model_service=cast(TaskDataModelService, test_data_model_service),
        git_repo_service=test_git_repo_service,
        environment_service=test_environment_service,
        project_service=test_project_service,
        task_sync_dir=test_settings_with_checks.task_sync_path,
        is_spawner_suppressed=True,
        anthropic_credentials_service=DefaultAnthropicCredentialsService(),
    )
    task_service.start()

    configuration_broadcast_service = DefaultConfigurationBroadcastService(
        data_model_service=test_data_model_service,
        task_service=task_service,
    )

    collection = CompleteServiceCollection(
        settings=test_settings_with_checks,
        data_model_service=test_data_model_service,
        task_service=task_service,
        environment_service=test_environment_service,
        secrets_service=test_secrets_service,
        git_repo_service=test_git_repo_service,
        local_sync_service=test_local_sync_service,
        project_service=test_project_service,
        anthropic_credentials_service=DefaultAnthropicCredentialsService(),
        configuration_broadcast_service=configuration_broadcast_service,
    )
    try:
        with collection.data_model_service.open_transaction(RequestID()) as transaction:
            transaction.upsert_project(project)
            collection.task_service.create_task(local_task, transaction)
        yield cast(ServiceCollectionForTask, collection)
    finally:
        collection.stop_all()


@pytest.fixture
def environment(
    tmp_path: Path,
    environment_config: LocalEnvironmentConfig,
    services: ServiceCollectionForTask,
    project: Project,
    initial_commit_repo: Path,
) -> Generator[LocalEnvironment, None, None]:
    code_dir, _ = initial_commit_repo
    image_config = LocalImageConfig(code_directory=code_dir)
    with tempfile.TemporaryDirectory() as tmp_dir:
        image = services.environment_service.ensure_image(image_config, project.object_id, {}, code_dir, Path(tmp_dir))
        with services.environment_service.generate_environment(
            image, project.object_id, environment_config
        ) as environment:
            yield environment


def get_all_messages_for_task(task_id: TaskID, services: ServiceCollectionForTask) -> list[Message]:
    all_messages: list[Message] = []
    with services.task_service.subscribe_to_task(task_id) as queue:
        while queue.qsize() > 0:
            all_messages.append(queue.get_nowait())
    # remove the initial task state message
    all_messages.pop(0)
    return all_messages
