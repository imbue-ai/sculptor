"""Data types for git repository service."""

from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.config.settings import SculptorSettings
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.workspace_service.api import WorkspaceService


class GitRepoServiceCollection(FrozenModel):
    # all service collections should have a settings object (makes it easy to serialize and deserialize them)
    settings: SculptorSettings
    # the actual services
    data_model_service: DataModelService
    dependency_management_service: DependencyManagementService
    git_repo_service: GitRepoService
    project_service: ProjectService
    workspace_service: WorkspaceService
