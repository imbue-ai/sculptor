"""Data types for git repository service."""

from imbue_core.pydantic_serialization import FrozenModel
from sculptor.config.settings import SculptorSettings
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentialsService
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.environment_service.api import EnvironmentService
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.secrets_service.api import SecretsService


class GitRepoServiceCollection(FrozenModel):
    # all service collections should have a settings object (makes it easy to serialize and deserialize them)
    settings: SculptorSettings
    # the actual services
    data_model_service: DataModelService
    environment_service: EnvironmentService
    secrets_service: SecretsService
    anthropic_credentials_service: AnthropicCredentialsService
    git_repo_service: GitRepoService
    project_service: ProjectService
