from pathlib import Path
from typing import Generator
from typing import cast

import pytest

from imbue_core.sculptor.user_config import UserConfig
from sculptor.config.settings import SculptorSettings
from sculptor.config.user_config import get_default_user_config_instance
from sculptor.config.user_config import set_user_config_instance
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentialsService
from sculptor.services.anthropic_credentials_service.default_implementation import DefaultAnthropicCredentialsService
from sculptor.services.anthropic_credentials_service.default_implementation import populate_credentials_file
from sculptor.services.configuration_broadcast_service.default_implementation import (
    DefaultConfigurationBroadcastService,
)
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService
from sculptor.services.environment_service.api import EnvironmentService
from sculptor.services.environment_service.default_implementation import DefaultEnvironmentService
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.default_implementation import DefaultGitRepoService
from sculptor.services.local_sync_service.default_implementation import DefaultLocalSyncService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.project_service.default_implementation import DefaultProjectService
from sculptor.services.secrets_service.api import SecretsService
from sculptor.services.secrets_service.local_implementation import LocalSecretsService
from sculptor.services.task_service.api import TaskService
from sculptor.services.task_service.threaded_implementation import LocalThreadTaskService


@pytest.fixture
def silly_global_config() -> Generator[UserConfig, None, None]:
    config = get_default_user_config_instance()
    config = config.model_copy(update={"is_suggestion_beta_feature_on": True})
    set_user_config_instance(config)
    yield config
    set_user_config_instance(None)


@pytest.fixture
def test_secrets_service(tmp_path: Path, silly_global_config: UserConfig) -> SecretsService:
    secret_file_path = tmp_path / ".sculptor/.env"
    service = LocalSecretsService(secret_file_path=secret_file_path)
    service.start()
    return service


@pytest.fixture
def test_anthropic_credentials_service(tmp_path: Path) -> AnthropicCredentialsService:
    credentials_file_path = tmp_path / ".sculptor" / "credentials.json"
    populate_credentials_file(
        credentials_file_path, AnthropicApiKey(anthropic_api_key="sk-ant-fake-api-key", generated_from_oauth=False)
    )
    service = DefaultAnthropicCredentialsService(credentials_file_path=credentials_file_path)
    return service


@pytest.fixture
def test_data_model_service(test_settings: SculptorSettings) -> DataModelService:
    service = SQLDataModelService.build_from_settings(test_settings)
    service.start()
    return service


@pytest.fixture
def test_git_repo_service() -> GitRepoService:
    service = DefaultGitRepoService()
    service.start()
    return service


@pytest.fixture
def test_project_service(test_settings: SculptorSettings, test_data_model_service: DataModelService) -> ProjectService:
    service = DefaultProjectService(settings=test_settings, data_model_service=test_data_model_service)
    service.start()
    return service


@pytest.fixture
def test_environment_service(
    test_settings: SculptorSettings,
    test_data_model_service: DataModelService,
    test_git_repo_service: GitRepoService,
    test_project_service: ProjectService,
) -> EnvironmentService:
    service = DefaultEnvironmentService(
        settings=test_settings,
        data_model_service=test_data_model_service,
        git_repo_service=test_git_repo_service,
    )
    service.start()
    return service


@pytest.fixture
def test_task_service(
    test_settings: SculptorSettings,
    test_secrets_service: SecretsService,
    test_anthropic_credentials_service: AnthropicCredentialsService,
    test_data_model_service: DataModelService,
    test_git_repo_service: GitRepoService,
    test_environment_service: EnvironmentService,
    test_project_service: ProjectService,
) -> TaskService:
    task_service = LocalThreadTaskService(
        settings=test_settings,
        secrets_service=test_secrets_service,
        anthropic_credentials_service=test_anthropic_credentials_service,
        data_model_service=cast(TaskDataModelService, test_data_model_service),
        git_repo_service=test_git_repo_service,
        environment_service=test_environment_service,
        project_service=test_project_service,
        task_sync_dir=test_settings.task_sync_path,
    )
    task_service.start()
    return task_service


@pytest.fixture
def test_local_sync_service(
    test_git_repo_service: GitRepoService,
    test_data_model_service: DataModelService,
    test_task_service: TaskService,
) -> DefaultLocalSyncService:
    service = DefaultLocalSyncService(
        git_repo_service=test_git_repo_service,
        data_model_service=test_data_model_service,
        task_service=test_task_service,
    )
    service.start()
    return service


@pytest.fixture
def test_service_collection(
    test_settings: SculptorSettings,
    test_secrets_service: SecretsService,
    test_anthropic_credentials_service: AnthropicCredentialsService,
    test_data_model_service: DataModelService,
    test_git_repo_service: GitRepoService,
    test_environment_service: EnvironmentService,
    test_task_service: TaskService,
    test_local_sync_service: DefaultLocalSyncService,
    test_project_service: ProjectService,
) -> Generator[CompleteServiceCollection, None, None]:
    configuration_broadcast_service = DefaultConfigurationBroadcastService(
        data_model_service=test_data_model_service,
        task_service=test_task_service,
    )

    collection = CompleteServiceCollection(
        settings=test_settings,
        data_model_service=test_data_model_service,
        task_service=test_task_service,
        environment_service=test_environment_service,
        secrets_service=test_secrets_service,
        anthropic_credentials_service=test_anthropic_credentials_service,
        git_repo_service=test_git_repo_service,
        local_sync_service=test_local_sync_service,
        project_service=test_project_service,
        configuration_broadcast_service=configuration_broadcast_service,
    )
    yield collection
    collection.stop_all()
