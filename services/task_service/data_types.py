from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.git_repo_service.data_types import GitRepoServiceCollection
from sculptor.services.task_service.api import TaskService


class TaskServiceCollection(GitRepoServiceCollection):
    task_service: TaskService


class ServiceCollectionForTask(TaskServiceCollection):
    data_model_service: TaskDataModelService
