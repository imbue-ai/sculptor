from typing import cast

from sculptor.config.settings import SculptorSettings
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.git_repo_service.service_collection import get_git_repo_service_collection
from sculptor.services.task_service.data_types import TaskServiceCollection
from sculptor.services.task_service.threaded_implementation import LocalThreadTaskService


def get_task_service_collection(settings: SculptorSettings) -> TaskServiceCollection:
    services = get_git_repo_service_collection(settings)
    task_service = LocalThreadTaskService(
        settings=settings,
        data_model_service=cast(TaskDataModelService, services.data_model_service),
        environment_service=services.environment_service,
        secrets_service=services.secrets_service,
        anthropic_credentials_service=services.anthropic_credentials_service,
        git_repo_service=services.git_repo_service,
        task_sync_dir=settings.task_sync_path,
        project_service=services.project_service,
    )

    return TaskServiceCollection(
        settings=settings,
        data_model_service=services.data_model_service,
        task_service=task_service,
        environment_service=services.environment_service,
        secrets_service=services.secrets_service,
        anthropic_credentials_service=services.anthropic_credentials_service,
        git_repo_service=services.git_repo_service,
        project_service=services.project_service,
    )
