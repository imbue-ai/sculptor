from abc import ABC
from abc import abstractmethod
from pathlib import Path

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.base import Environment
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs


class EnvironmentManager(ABC):
    """
    Internal component for managing environment lifecycle.

    This class is an implementation detail of WorkspaceService and should not be
    accessed directly from outside the workspace_service module.

    Environments are created directly from project paths - no image concept needed
    since we work directly in the user's repository.

    This class will automatically clean up any previous environments when it is started.
    This is required for correctness in the face of hard crashes or unexpected shutdowns.
    """

    @abstractmethod
    def create_environment(
        self,
        project_path: Path,
        project_id: ProjectID,
        concurrency_group: ConcurrencyGroup,
        vcs: WorkspaceVcs,
        workspace_id: WorkspaceID,
        initialization_strategy: WorkspaceInitializationStrategy,
        source_branch: str | None = None,
        requested_branch_name: str | None = None,
        env_var_override: bool = False,
    ) -> Environment:
        """
        Create a new environment for a project.

        Args:
            project_path: Path to the project's repository.
            project_id: ID of the project.
            concurrency_group: Concurrency group for process management.
            vcs: The workspace's version control, which creates its checkout.
            workspace_id: The workspace the environment belongs to; it names the checkout.
            initialization_strategy: Strategy for workspace initialization.
            source_branch: The ref the checkout starts from.
            requested_branch_name: The ref created for the workspace.
            env_var_override: Whether project env vars override os.environ on collision.

        Returns:
            A new Environment instance.
        """

    @abstractmethod
    def resume_environment(
        self,
        environment_id: str,
        project_path: Path,
        project_id: ProjectID,
        concurrency_group: ConcurrencyGroup,
        vcs: WorkspaceVcs,
        workspace_id: WorkspaceID,
        initialization_strategy: WorkspaceInitializationStrategy,
        env_var_override: bool = False,
        sculptor_folder: Path | None = None,
    ) -> Environment:
        """
        Resume an existing environment by its ID.

        Args:
            environment_id: The environment ID (workspace path) to resume.
            project_path: Path to the project's repository.
            project_id: ID of the project.
            concurrency_group: Concurrency group for process management.
            vcs: The workspace's version control, which verifies its checkout.
            workspace_id: The workspace the environment belongs to; it names the checkout.
            initialization_strategy: Strategy for workspace initialization.
            env_var_override: Whether project env vars override os.environ on collision.
            sculptor_folder: Override for the sculptor folder path (uses get_workspaces_folder() if None).

        Returns:
            The resumed Environment instance.

        Raises:
            EnvironmentNotFoundError: if the environment doesn't exist or `vcs` finds its checkout unusable.
            EnvironmentConfigurationChangedError: if environment config has changed.
        """

    @abstractmethod
    def cleanup_stale_environments(self) -> None:
        """
        Clean up stale environments that are no longer needed.
        """

    @abstractmethod
    def delete_environment(self, environment_id: str) -> None:
        """
        Delete a specific environment by its ID.

        This should be called when a task is deleted to clean up its environment.

        Args:
            environment_id: The environment ID (working-directory path) to delete.
        """
