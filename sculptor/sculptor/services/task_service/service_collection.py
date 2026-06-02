from typing import cast

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.config.settings import SculptorSettings
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.git_repo_service.service_collection import get_git_repo_service_collection
from sculptor.services.task_service.data_types import TaskServiceCollection
from sculptor.services.task_service.threaded_implementation import LocalThreadTaskService


def get_task_service_collection(
    concurrency_group: ConcurrencyGroup,
    settings: SculptorSettings,
) -> TaskServiceCollection:
    services = get_git_repo_service_collection(concurrency_group, settings)
    task_service = LocalThreadTaskService(
        concurrency_group=concurrency_group.make_concurrency_group("task_service"),
        settings=settings,
        data_model_service=cast(TaskDataModelService, services.data_model_service),
        dependency_management_service=services.dependency_management_service,
        git_repo_service=services.git_repo_service,
        task_sync_dir=settings.task_sync_path,
        project_service=services.project_service,
        workspace_service=services.workspace_service,
    )

    return TaskServiceCollection(
        settings=settings,
        data_model_service=services.data_model_service,
        dependency_management_service=services.dependency_management_service,
        task_service=task_service,
        git_repo_service=services.git_repo_service,
        project_service=services.project_service,
        workspace_service=services.workspace_service,
    )
