from abc import ABC
from abc import abstractmethod
from pathlib import Path

from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.environments.base import Environment


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
        initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.IN_PLACE,
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
            initialization_strategy: Strategy for workspace initialization.
            source_branch: Branch to checkout after cloning (for CLONE mode) or base
                ref off which to create the worktree branch (for WORKTREE mode).
            requested_branch_name: For WORKTREE mode, the new branch name created by
                `git worktree add -b`; required for WORKTREE, unused otherwise.
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
        initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.IN_PLACE,
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
            initialization_strategy: Strategy for workspace initialization.
            env_var_override: Whether project env vars override os.environ on collision.
            sculptor_folder: Override for the sculptor folder path (uses get_workspaces_folder() if None).

        Returns:
            The resumed Environment instance.

        Raises:
            EnvironmentNotFoundError: if the environment doesn't exist.
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
