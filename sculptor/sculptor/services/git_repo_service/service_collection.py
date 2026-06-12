from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.config.settings import SculptorSettings
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.git_repo_service.data_types import GitRepoServiceCollection
from sculptor.services.git_repo_service.default_implementation import DefaultGitRepoService
from sculptor.services.project_service.default_implementation import DefaultProjectService
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService


def get_git_repo_service_collection(
    concurrency_group: ConcurrencyGroup,
    settings: SculptorSettings,
) -> GitRepoServiceCollection:
    data_model_service = SQLDataModelService.build_from_settings(
        settings, concurrency_group.make_concurrency_group("data_model_service")
    )
    dependency_management_service = DependencyManagementService(
        concurrency_group=concurrency_group.make_concurrency_group("dependency_management_service"),
    )
    git_repo_service = DefaultGitRepoService(
        concurrency_group=concurrency_group.make_concurrency_group("git_repo_service")
    )
    project_service = DefaultProjectService(
        concurrency_group=concurrency_group.make_concurrency_group("project_service"),
        data_model_service=data_model_service,
    )
    workspace_service = DefaultWorkspaceService.build(
        concurrency_group=concurrency_group,
        settings=settings,
        data_model_service=data_model_service,
        project_service=project_service,
        dependency_management_service=dependency_management_service,
    )
    return GitRepoServiceCollection(
        settings=settings,
        data_model_service=data_model_service,
        dependency_management_service=dependency_management_service,
        git_repo_service=git_repo_service,
        project_service=project_service,
        workspace_service=workspace_service,
    )
