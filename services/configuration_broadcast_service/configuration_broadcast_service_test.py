import json
import tempfile
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from sculptor.database.models import ProjectID
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import UserReference
from sculptor.services.configuration_broadcast_service.api import ProjectConfiguration
from sculptor.services.configuration_broadcast_service.api import UserConfiguration
from sculptor.services.configuration_broadcast_service.default_implementation import (
    DefaultConfigurationBroadcastService,
)
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.task_service.api import TaskService


@pytest.fixture
def mock_data_model_service() -> Mock:
    mock_service = Mock(spec=TaskDataModelService)
    mock_transaction = Mock()
    mock_service.open_task_transaction.return_value.__enter__ = Mock(return_value=mock_transaction)
    mock_service.open_task_transaction.return_value.__exit__ = Mock(return_value=None)
    mock_transaction.get_all_tasks.return_value = []
    mock_transaction.get_tasks_for_project.return_value = []
    return mock_service


@pytest.fixture
def mock_task_service() -> Mock:
    mock_service = Mock(spec=TaskService)
    return mock_service


@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def configuration_service(
    mock_data_model_service: Mock,
    mock_task_service: Mock,
    temp_config_dir: Path,
) -> DefaultConfigurationBroadcastService:
    service = DefaultConfigurationBroadcastService(
        data_model_service=mock_data_model_service,
        task_service=mock_task_service,
    )
    service._config_dir = temp_config_dir
    service._user_config_file = temp_config_dir / "user_config.json"
    service._project_config_file = temp_config_dir / "project_config.json"
    return service


@pytest.fixture
def sample_user_config() -> UserConfiguration:
    return UserConfiguration()


@pytest.fixture
def sample_project_config() -> ProjectConfiguration:
    return ProjectConfiguration(
        gitlab_token="project_token_456",
        gitlab_url="https://gitlab.example.com/project",
        token_expires_at_iso="2024-12-31T23:59:59",
    )


@pytest.fixture
def sample_project_id() -> ProjectID:
    return ProjectID()


@pytest.fixture
def sample_task_id() -> TaskID:
    return TaskID()


@pytest.fixture
def sample_tasks() -> list[Task]:
    task1 = Mock(spec=Task)
    task1.object_id = TaskID()
    task1.project_id = ProjectID()
    task1.organization_reference = OrganizationReference("test_org")
    task1.user_reference = UserReference("test_user")
    task1.is_deleted = False

    task2 = Mock(spec=Task)
    task2.object_id = TaskID()
    task2.project_id = ProjectID()
    task2.organization_reference = OrganizationReference("test_org")
    task2.user_reference = UserReference("test_user")
    task2.is_deleted = False

    return [task1, task2]


def test_get_current_user_configuration_empty(configuration_service: DefaultConfigurationBroadcastService):
    config = configuration_service.get_current_user_configuration()
    assert isinstance(config, UserConfiguration)


def test_get_current_user_configuration_with_data(configuration_service: DefaultConfigurationBroadcastService):
    config = configuration_service.get_current_user_configuration()
    assert isinstance(config, UserConfiguration)


def test_get_current_project_configuration_empty(
    configuration_service: DefaultConfigurationBroadcastService, sample_project_id: ProjectID
):
    config = configuration_service.get_current_project_configuration(sample_project_id)
    assert config.gitlab_token is None
    assert config.gitlab_url is None
    assert config.token_expires_at_iso is None


def test_get_current_project_configuration_with_data(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_project_id: ProjectID,
    sample_project_config: ProjectConfiguration,
):
    configuration_service._project_configurations = {
        str(sample_project_id): {
            "gitlab_token": sample_project_config.gitlab_token,
            "gitlab_url": sample_project_config.gitlab_url,
            "token_expires_at_iso": sample_project_config.token_expires_at_iso,
        }
    }

    config = configuration_service.get_current_project_configuration(sample_project_id)
    assert config.gitlab_token == sample_project_config.gitlab_token
    assert config.gitlab_url == sample_project_config.gitlab_url
    assert config.token_expires_at_iso == sample_project_config.token_expires_at_iso


def test_send_configuration_to_task_with_config(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_task_id: TaskID,
    sample_user_config: UserConfiguration,
):
    configuration_service.send_configuration_to_task(sample_task_id, sample_user_config)

    configuration_service.task_service.create_message.assert_called_once()
    message, task_id, _ = configuration_service.task_service.create_message.call_args[0]
    assert task_id == sample_task_id
    assert message.object_type == "SetUserConfigurationDataUserMessage"


def test_send_configuration_to_task_no_config(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_task_id: TaskID,
):
    empty_config = UserConfiguration()
    configuration_service.send_configuration_to_task(sample_task_id, empty_config)

    configuration_service.task_service.create_message.assert_called_once()
    message, task_id, _ = configuration_service.task_service.create_message.call_args[0]
    assert task_id == sample_task_id
    assert message.object_type == "SetUserConfigurationDataUserMessage"


def test_broadcast_configuration_to_all_tasks(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_user_config: UserConfiguration,
    sample_tasks: list[Task],
):
    mock_transaction = (
        configuration_service.data_model_service.open_task_transaction.return_value.__enter__.return_value
    )
    mock_transaction.get_all_tasks.return_value = sample_tasks

    configuration_service.broadcast_configuration_to_all_tasks(sample_user_config)

    assert configuration_service.task_service.create_message.call_count == len(sample_tasks)

    for task in sample_tasks:
        calls = configuration_service.task_service.create_message.call_args_list
        task_ids = [call[0][1] for call in calls]
        assert task.object_id in task_ids


def test_send_configuration_to_project(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_project_id: ProjectID,
    sample_project_config: ProjectConfiguration,
    sample_tasks: list[Task],
):
    mock_transaction = (
        configuration_service.data_model_service.open_task_transaction.return_value.__enter__.return_value
    )
    mock_transaction.get_tasks_for_project.return_value = sample_tasks

    configuration_service.send_configuration_to_project(sample_project_id, sample_project_config)

    assert configuration_service.task_service.create_message.call_count == len(sample_tasks)

    for task in sample_tasks:
        calls = configuration_service.task_service.create_message.call_args_list
        task_ids = [call[0][1] for call in calls]
        assert task.object_id in task_ids


def test_send_configuration_to_project_no_config(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_project_id: ProjectID,
):
    empty_config = ProjectConfiguration()
    configuration_service.send_configuration_to_project(sample_project_id, empty_config)

    configuration_service.task_service.create_message.assert_not_called()


def test_rebroadcast_current_configuration_to_task_with_config(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_task_id: TaskID,
):
    configuration_service.rebroadcast_current_configuration_to_task(sample_task_id)

    configuration_service.task_service.create_message.assert_called_once()
    message, task_id, _ = configuration_service.task_service.create_message.call_args[0]
    assert task_id == sample_task_id
    assert message.object_type == "SetUserConfigurationDataUserMessage"


def test_rebroadcast_current_configuration_to_task_no_config(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_task_id: TaskID,
):
    configuration_service.rebroadcast_current_configuration_to_task(sample_task_id)

    configuration_service.task_service.create_message.assert_called_once()
    message, task_id, _ = configuration_service.task_service.create_message.call_args[0]
    assert task_id == sample_task_id
    assert message.object_type == "SetUserConfigurationDataUserMessage"


def test_configuration_file_loading_user_config(configuration_service: DefaultConfigurationBroadcastService):
    user_config_data = {
        "configuration": {
            "gitlab_token": "loaded_token_123",
            "gitlab_url": "https://gitlab.loaded.com",
            "token_expires_at_iso": "2024-12-31T23:59:59",
        }
    }
    with open(configuration_service._user_config_file, "w") as f:
        json.dump(user_config_data, f)

    configuration_service._load_user_configuration()

    assert configuration_service._user_configuration["gitlab_token"] == "loaded_token_123"
    assert configuration_service._user_configuration["gitlab_url"] == "https://gitlab.loaded.com"
    assert configuration_service._user_configuration["token_expires_at_iso"] == "2024-12-31T23:59:59"


def test_configuration_file_loading_project_config(configuration_service: DefaultConfigurationBroadcastService):
    project_id = ProjectID()

    project_config_data = {
        "project_configurations": {
            str(project_id): {
                "gitlab_token": "project_token_789",
                "gitlab_url": "https://gitlab.project.com",
                "token_expires_at_iso": "2024-12-31T23:59:59",
            }
        }
    }
    with open(configuration_service._project_config_file, "w") as f:
        json.dump(project_config_data, f)

    configuration_service._load_project_configurations()

    project_config = configuration_service._project_configurations[str(project_id)]
    assert project_config["gitlab_token"] == "project_token_789"
    assert project_config["gitlab_url"] == "https://gitlab.project.com"
    assert project_config["token_expires_at_iso"] == "2024-12-31T23:59:59"


def test_configuration_file_loading_missing_files(configuration_service: DefaultConfigurationBroadcastService):
    configuration_service._load_user_configuration()
    configuration_service._load_project_configurations()

    assert configuration_service._user_configuration == {}
    assert configuration_service._project_configurations == {}


def test_configuration_file_loading_invalid_json(configuration_service: DefaultConfigurationBroadcastService):
    with open(configuration_service._user_config_file, "w") as f:
        f.write("invalid json content")

    with open(configuration_service._project_config_file, "w") as f:
        f.write("invalid json content")

        configuration_service._load_user_configuration()
        configuration_service._load_project_configurations()

    assert configuration_service._user_configuration == {}
    assert configuration_service._project_configurations == {}


def test_is_token_expired_no_expiration(configuration_service: DefaultConfigurationBroadcastService):
    config = ProjectConfiguration()
    assert configuration_service.is_token_expired(config)


def test_is_token_expired_future_date(configuration_service: DefaultConfigurationBroadcastService):
    config = ProjectConfiguration(token_expires_at_iso="2030-12-31T23:59:59")
    assert not configuration_service.is_token_expired(config)


def test_is_token_expired_past_date(configuration_service: DefaultConfigurationBroadcastService):
    config = ProjectConfiguration(token_expires_at_iso="2020-01-01T00:00:00")
    assert configuration_service.is_token_expired(config)


def test_is_token_expired_expiring_soon(configuration_service: DefaultConfigurationBroadcastService):
    tomorrow = (datetime.now() + timedelta(hours=12)).isoformat()
    config = ProjectConfiguration(token_expires_at_iso=tomorrow)
    assert configuration_service.is_token_expired(config)


@patch("sculptor.services.configuration_broadcast_service.default_implementation.get_sculptor_folder")
def test_service_initialization(mock_get_sculptor_folder, mock_data_model_service, mock_task_service):
    mock_config_dir = Path("/tmp/test_config")
    mock_get_sculptor_folder.return_value = mock_config_dir

    service = DefaultConfigurationBroadcastService(
        data_model_service=mock_data_model_service,
        task_service=mock_task_service,
    )

    assert service._config_dir == mock_config_dir / "configuration"
    assert service._user_config_file == mock_config_dir / "configuration" / "user_config.json"
    assert service._project_config_file == mock_config_dir / "configuration" / "project_config.json"
    assert service.data_model_service == mock_data_model_service
    assert service.task_service == mock_task_service


def test_message_creation_user_config(
    configuration_service: DefaultConfigurationBroadcastService, sample_user_config: UserConfiguration
):
    message = configuration_service._create_configuration_message(sample_user_config)

    assert message.object_type == "SetUserConfigurationDataUserMessage"


def test_message_creation_project_config(
    configuration_service: DefaultConfigurationBroadcastService,
    sample_project_id: ProjectID,
    sample_project_config: ProjectConfiguration,
):
    message = configuration_service._create_project_configuration_message(sample_project_id, sample_project_config)

    assert message.gitlab_token == sample_project_config.gitlab_token
    assert message.gitlab_url == sample_project_config.gitlab_url
    assert message.object_type == "SetProjectConfigurationDataUserMessage"
