from sculptor.config.settings import SculptorSettings
from sculptor.services.anthropic_credentials_service.default_implementation import DefaultAnthropicCredentialsService
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService
from sculptor.services.environment_service.default_implementation import DefaultEnvironmentService
from sculptor.services.git_repo_service.data_types import GitRepoServiceCollection
from sculptor.services.git_repo_service.default_implementation import DefaultGitRepoService
from sculptor.services.project_service.default_implementation import DefaultProjectService
from sculptor.services.secrets_service.local_implementation import LocalSecretsService


def get_git_repo_service_collection(settings: SculptorSettings) -> GitRepoServiceCollection:
    data_model_service = SQLDataModelService.build_from_settings(settings)
    git_repo_service = DefaultGitRepoService()
    project_service = DefaultProjectService(
        settings=settings,
        data_model_service=data_model_service,
    )
    environment_service = DefaultEnvironmentService(
        settings=settings,
        data_model_service=data_model_service,
        git_repo_service=git_repo_service,
    )
    return GitRepoServiceCollection(
        settings=settings,
        environment_service=environment_service,
        data_model_service=data_model_service,
        secrets_service=LocalSecretsService(),
        anthropic_credentials_service=DefaultAnthropicCredentialsService(),
        git_repo_service=git_repo_service,
        project_service=project_service,
    )
