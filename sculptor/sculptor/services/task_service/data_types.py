from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.git_repo_service.data_types import GitRepoServiceCollection
from sculptor.services.task_service.api import TaskService


class TaskServiceCollection(GitRepoServiceCollection):
    """Service collection extended with the task service."""

    task_service: TaskService


class ServiceCollectionForTask(TaskServiceCollection):
    """Service collection available to task handlers, with task-scoped data model access."""

    data_model_service: TaskDataModelService
