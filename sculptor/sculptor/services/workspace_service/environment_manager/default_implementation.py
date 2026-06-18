import shutil
from pathlib import Path
from uuid import uuid4

from loguru import logger

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import MutableModel
from sculptor.interfaces.environments.base import Environment
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.workspace_service.environment_manager.api import EnvironmentManager
from sculptor.services.workspace_service.environment_manager.env_file_parser import atomic_copy_env_file
from sculptor.services.workspace_service.environment_manager.env_file_parser import load_project_env_vars
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.utils.build import get_workspaces_folder

# Workspace directory for local environments
LOCAL_WORKSPACE_DIR = get_workspaces_folder()


def _create_workspace_path(workspace_path_id: str) -> Path:
    """Create a new workspace directory and return its path."""
    workspace_path = LOCAL_WORKSPACE_DIR / workspace_path_id
    workspace_path.mkdir(parents=True, exist_ok=True)
    return workspace_path


def _cleanup_workspace(workspace_path: Path) -> None:
    """Remove a specific workspace directory."""
    if workspace_path.exists() and workspace_path.is_dir():
        logger.debug("Cleaning up workspace: {}", workspace_path)
        shutil.rmtree(workspace_path, ignore_errors=True)


class DefaultEnvironmentManager(MutableModel, EnvironmentManager):
    """Internal environment manager that creates local environments directly.

    This class is an implementation detail of WorkspaceService and should not be
    accessed directly from outside the workspace_service module.

    It works directly in the user's repository without any code copying.
    A workspace directory is created only for state/artifacts.
    """

    data_model_service: TaskDataModelService

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
        """Create a new local environment.

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
            A LocalEnvironment instance.
        """
        # Create workspace for state/artifacts only
        workspace_path = _create_workspace_path(uuid4().hex)

        return LocalEnvironment.create(
            environment_id=LocalEnvironmentID(str(workspace_path)),
            concurrency_group=concurrency_group,
            project_id=project_id,
            repo_host_path=project_path,
            initialization_strategy=initialization_strategy,
            source_branch=source_branch,
            requested_branch_name=requested_branch_name,
            env_var_override=env_var_override,
        )

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
        """Resume an existing environment by its ID (workspace path).

        Args:
            environment_id: The environment ID (workspace path) to resume.
            project_path: Path to the project's repository.
            project_id: ID of the project.
            concurrency_group: Concurrency group for process management.
            initialization_strategy: Strategy for workspace initialization.
            env_var_override: Whether project env vars override os.environ on collision.
            sculptor_folder: Override for the sculptor folder path (uses get_workspaces_folder() if None).

        Returns:
            A LocalEnvironment instance.
        """
        env = LocalEnvironment(
            environment_id=LocalEnvironmentID(environment_id),
            project_id=project_id,
            concurrency_group=concurrency_group,
            repo_host_path=project_path,
            initialization_strategy=initialization_strategy,
        )
        # For clone mode, re-copy .sculptor/.env from the source repo so that
        # edits made since the clone was created are picked up on resume.
        if initialization_strategy == WorkspaceInitializationStrategy.CLONE:
            source_env_file = project_path / ".sculptor" / ".env"
            dest_env_file = env.get_working_directory() / ".sculptor" / ".env"
            if source_env_file.exists():
                atomic_copy_env_file(source_env_file, dest_env_file)
            elif dest_env_file.exists():
                dest_env_file.unlink()
        env._sculptor_folder = sculptor_folder
        env._project_env_vars = load_project_env_vars(env.get_working_directory(), sculptor_folder=sculptor_folder)
        env._env_var_override = env_var_override
        return env

    def delete_environment(self, environment_id: str) -> None:
        """Delete a specific environment by its ID.

        This should be called when a task is deleted to clean up its workspace.
        """
        workspace_path = Path(environment_id)
        if workspace_path.exists():
            logger.debug("Deleting environment workspace: {}", workspace_path)
            _cleanup_workspace(workspace_path)
        else:
            logger.debug("Environment workspace already deleted or doesn't exist: {}", workspace_path)

    def cleanup_stale_environments(self) -> None:
        """Clean up stale environments (workspaces) that are no longer needed.

        Only deletes workspaces that are NOT associated with any active (non-deleted) workspace.
        Workspace is the single owner of environment, so we query workspaces directly.
        """
        # Get environment_ids of all active workspaces (non-deleted)
        active_environment_ids: set[str] = set()
        with self.data_model_service.open_task_transaction() as transaction:
            # get_workspaces() returns non-deleted workspaces
            all_workspaces = transaction.get_workspaces()
            for workspace in all_workspaces:
                if workspace.environment_id is not None:
                    active_environment_ids.add(workspace.environment_id)

        # Clean up workspaces not associated with active workspaces
        if not LOCAL_WORKSPACE_DIR.exists():
            return

        for workspace_dir in LOCAL_WORKSPACE_DIR.iterdir():
            if workspace_dir.is_dir() and not workspace_dir.name.startswith("."):
                workspace_path_str = str(workspace_dir)
                if workspace_path_str not in active_environment_ids:
                    logger.debug("Cleaning up stale workspace: {}", workspace_dir)
                    _cleanup_workspace(workspace_dir)
                else:
                    logger.debug("Preserving active workspace: {}", workspace_dir)
