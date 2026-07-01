from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from typing import Literal
from typing import TYPE_CHECKING

from sculptor.database.models import Project
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.errors import ExpectedError
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.service import Service

if TYPE_CHECKING:
    from queue import Queue

    # Imported only for type-checking: web.data_types imports this module, so a
    # runtime import here would cycle.
    from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.workspace_service.setup_command_runner import SetupStateProvider

# The default workspace setup command when a project has not configured one.
# Fetches the origin remote if present; succeeds silently if origin is missing
# (e.g. repos without an `origin` remote) so workspace startup isn't blocked.
DEFAULT_WORKSPACE_SETUP_COMMAND = "git fetch origin 2>/dev/null || true"


def resolve_workspace_setup_command(stored_command: str | None) -> str | None:
    """Resolve a project's stored setup command to the command that should actually run.

    Tri-state semantics:
    - ``None``: project has never been configured → run the current default.
    - ``""``: user explicitly cleared the command → run nothing.
    - other string: user's custom command → run as-is.
    """
    if stored_command is None:
        return DEFAULT_WORKSPACE_SETUP_COMMAND
    if stored_command == "":
        return None
    return stored_command


class GitOperationResult(FrozenModel):
    """Result of a git operation (commit, etc.)."""

    success: bool
    stdout: str
    stderr: str
    error_message: str | None = None


class FileAtRefResult(FrozenModel):
    """Result of reading a file at a specific git ref."""

    content: str
    encoding: Literal["utf-8", "base64"]


class CommitFileChange(FrozenModel):
    """Per-file change within a single commit."""

    path: str
    status: Literal["M", "A", "D", "R"]
    old_path: str | None
    additions: int
    deletions: int


class CommitRecord(FrozenModel):
    """A single commit in a workspace branch's history."""

    hash: str
    short_hash: str
    message: str
    author_name: str
    author_email: str
    timestamp: str
    parent_hashes: list[str]
    files: list[CommitFileChange]


class WorkspaceNotFoundError(ExpectedError):
    """Raised when a workspace is not found."""

    def __init__(self, workspace_id: WorkspaceID) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"Workspace not found: {workspace_id}")


class FileNotFoundAtRefError(ExpectedError):
    """Raised when a file is not found at a specific git ref."""

    def __init__(self, file_path: str, git_ref: str, detail: str = "") -> None:
        self.file_path = file_path
        self.git_ref = git_ref
        super().__init__(f"File {file_path} not found at ref {git_ref}: {detail}")


class WorkspaceFilesUnavailableError(ExpectedError):
    """Raised when the workspace file list cannot be produced right now.

    Distinguishes a transient git failure (e.g. lock contention while another
    process is writing the index) from a workspace that legitimately contains
    no files. Callers should surface this as a retryable error rather than as
    an empty result. Tracked in SCU-1263.
    """

    def __init__(self, workspace_id: WorkspaceID, detail: str = "") -> None:
        self.workspace_id = workspace_id
        super().__init__(f"Workspace files unavailable for {workspace_id}: {detail}")


class WorkspaceService(Service, ABC):
    """
    Manages workspace lifecycle and environment ownership.

    Workspace is the single owner of environment lifecycle. This service:
    - Creates and manages workspaces for projects
    - Manages environment creation/resumption through agent_environment_context
    - Handles workspace deletion
    - Delegates to EnvironmentManager for low-level environment operations

    Note: get_workspace and get_workspaces are NOT on this service.
    These are simple database lookups that should use transaction.get_workspace()
    and transaction.get_workspaces() directly.
    """

    @abstractmethod
    def add_observer(self, queue: "Queue[StreamingUpdateSourceTypes]") -> None:
        """Subscribe a queue to per-workspace git state (current branch, target branches).

        Backfills current state immediately, then pushes updates as the branch
        scan detects them. A single process-global scanner serves all observers,
        so websocket streams subscribe here rather than each starting their own
        per-workspace pollers. Per-connection scope filtering is the caller's job.
        """

    @abstractmethod
    def remove_observer(self, queue: "Queue[StreamingUpdateSourceTypes]") -> None:
        """Unsubscribe a queue previously passed to ``add_observer``."""

    # Workspace Operations

    @abstractmethod
    def create_workspace(
        self,
        project: Project,
        initialization_strategy: WorkspaceInitializationStrategy,
        source_branch: str | None,
        requested_branch_name: str | None,
        description: str | None,
        transaction: DataModelTransaction,
        target_branch: str | None = None,
    ) -> Workspace:
        """
        Create a new workspace for a project.

        Args:
            project: The project to create the workspace for.
            initialization_strategy: Strategy for workspace initialization (IN_PLACE, CLONE, or WORKTREE).
            source_branch: Branch to use for CLONE strategy, or base ref for WORKTREE.
            requested_branch_name: Final branch name; required for WORKTREE, optional
                for CLONE, must be None for IN_PLACE.
            description: Optional description for the workspace.
            transaction: Database transaction for atomicity.
            target_branch: Diff/merge target branch. When None, a default is resolved
                from the repo (origin's default branch, else local main/master).

        Returns:
            The created Workspace.
        """

    @abstractmethod
    def make_setup_state_provider(self, workspace_id: str) -> SetupStateProvider:
        """Build a workspace-scoped provider for the agent setup-reminder feature.

        The provider asks ``SetupCommandRunner`` for the absolute setup-log
        path internally — callers never need to compute workspace state
        directories themselves.
        """

    @abstractmethod
    def update_workspace(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
        description: str | None = None,
        target_branch: str | None = None,
        is_open: bool | None = None,
    ) -> Workspace:
        """
        Update a workspace's description, target branch, and/or open state.

        Args:
            workspace_id: The ID of the workspace to update.
            transaction: Database transaction for atomicity.
            description: The new description for the workspace, if updating.
            target_branch: The new target branch for the workspace, if updating.
            is_open: The new open/closed state for the workspace, if updating.

        Returns:
            The updated Workspace.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    @abstractmethod
    def delete_workspace(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
    ) -> None:
        """
        Delete a workspace and its associated environment.

        Args:
            workspace_id: The ID of the workspace to delete.
            transaction: Database transaction for atomicity.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    # Environment Lifecycle

    @abstractmethod
    @contextmanager
    def agent_environment_context(
        self,
        project: Project,
        workspace_id: WorkspaceID,
        task_id: TaskID,
        concurrency_group: ConcurrencyGroup,
        root_progress_handle: RootProgressHandle,
        shutdown_event: ReadOnlyEvent,
    ) -> Generator[AgentExecutionEnvironment, None, None]:
        """
        Set up the environment for a workspace.

        Creates or resumes a LocalEnvironment for the workspace and wraps it in
        an AgentExecutionEnvironment that provides per-task namespaced paths.

        Workspace is the single owner of environment lifecycle. This method:
        - Resumes an existing environment if workspace.environment_id is set
        - Creates a new environment otherwise
        - Updates workspace.environment_id after creation
        - Wraps the environment in AgentExecutionEnvironment for the task
        - Cleans up the environment on context exit if the workspace was deleted

        Per-task namespacing (via AgentExecutionEnvironment):
        - State path: {workspace_root}/state/tasks/{task_id}/
        - Artifacts path: {workspace_root}/artifacts/tasks/{task_id}/
        - Workspace path: Shared code directory

        Args:
            project: The project containing the workspace.
            workspace_id: The workspace to set up environment for.
            task_id: The task requesting the environment (for per-task namespacing).
            concurrency_group: Concurrency group for process management.
            root_progress_handle: Progress handle for tracking setup.
            shutdown_event: Event to signal shutdown.

        Yields:
            The AgentExecutionEnvironment instance for the task.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    # Workspace Diff Operations

    @abstractmethod
    def refresh_workspace_diff(
        self,
        workspace_id: WorkspaceID,
        context_lines: int | None = None,
        include_target_branch_diff: bool = False,
    ) -> None:
        """
        Regenerate workspace diff and store it. Always generates a new diff.

        Acquires a per-workspace lock (non-blocking) to prevent concurrent generation.
        If the lock is already held, returns immediately. Manages its own transactions
        for each status transition (GENERATING -> READY) so the frontend sees each
        state change immediately.

        The diff is computed from workspace.source_git_hash to current state and
        stored in the workspace artifacts directory.

        Args:
            workspace_id: The workspace to refresh diff for.
            context_lines: Number of unchanged context lines around each diff hunk.
            include_target_branch_diff: Whether to also generate a diff from the
                workspace's target branch to the current working tree.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    @abstractmethod
    def maybe_refresh_workspace_diff(
        self,
        workspace_id: WorkspaceID,
    ) -> None:
        """
        Regenerate workspace diff if needed (e.g., files changed).

        Called by agents after file modifications. For now, always refreshes.
        In the future, may check if files actually changed before regenerating.

        Args:
            workspace_id: The workspace to potentially refresh diff for.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    @abstractmethod
    def mark_workspace_diff_stale(
        self,
        workspace_id: WorkspaceID,
    ) -> None:
        """
        Signal the frontend that a diff is available without generating it.

        Sets diff_status=READY and diff_updated_at=now() so the frontend's
        useWorkspaceDiffSync hook triggers a fetch. The actual diff artifact is
        generated on-demand when the frontend calls GET /workspaces/{id}/diff.

        Used at agent startup to avoid blocking on expensive git diff commands
        during the critical path.

        Args:
            workspace_id: The workspace to mark.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    @abstractmethod
    def get_workspace_diff(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
        force_refresh: bool = False,
        context_lines: int | None = None,
        include_target_branch_diff: bool = False,
    ) -> DiffArtifact | None:
        """
        Get the latest stored diff artifact for the workspace.

        Does NOT regenerate by default - just reads from workspace artifacts directory.
        If force_refresh=True, regenerates before returning.

        The generation timestamp is available via workspace.diff_updated_at.

        Args:
            workspace_id: The workspace to get diff for.
            transaction: Database transaction for atomicity.
            force_refresh: If True, regenerate diff before returning.
            context_lines: Number of unchanged context lines around each diff hunk.
            include_target_branch_diff: If True, compute and include the target branch diff.

        Returns:
            The diff artifact, or None if no diff has been generated yet.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    # Workspace Directory Resolution

    @abstractmethod
    def get_workspace_working_directory(
        self,
        workspace: Workspace,
        transaction: DataModelTransaction | None = None,
    ) -> Path | None:
        """
        Get the git working directory for a workspace.

        For IN_PLACE workspaces, returns the project's local path.
        For CLONE workspaces, returns the cloned repository path inside the environment.
        Returns None if the workspace's environment hasn't been initialized yet.

        Args:
            workspace: The workspace to get the working directory for.
            transaction: Optional existing transaction to reuse for project lookup.

        Returns:
            The working directory path, or None if the environment isn't ready.
        """

    @abstractmethod
    def get_persistent_task_artifacts_dir(
        self,
        workspace_id: WorkspaceID,
        task_id: TaskID,
    ) -> Path | None:
        """Return the on-disk directory where the agent writes per-task artifact
        snapshots for the given task, or None if the workspace's environment
        has not been initialized yet.

        This is the stable, source-of-truth location: {workspace_root}/artifacts/tasks/{task_id}/
        — distinct from the host-side task_sync cache, which is a latest-only
        mirror that can be wiped without losing data. Used by the task service
        to backfill the cache when it is missing (SCU-1245).
        """

    # Workspace Git Operations

    @abstractmethod
    def discard_file(
        self,
        workspace_id: WorkspaceID,
        file_path: str,
        transaction: DataModelTransaction,
    ) -> GitOperationResult:
        """Discard changes to a single file in the workspace.

        Validates the file path, runs git checkout (tracked) or git clean (untracked),
        and refreshes the workspace diff afterward.

        Args:
            workspace_id: The workspace containing the file.
            file_path: Relative path to the file within the workspace.
            transaction: Database transaction for atomicity.

        Returns:
            Result of the git operation.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    @abstractmethod
    def get_commit_diff(
        self,
        workspace_id: WorkspaceID,
        commit_hash: str,
        transaction: DataModelTransaction,
    ) -> tuple[str, str, str | None]:
        """Get the unified diff for a single commit.

        Args:
            workspace_id: The workspace containing the commit.
            commit_hash: The hex hash of the commit to diff.
            transaction: Database transaction for atomicity.

        Returns:
            Tuple of (diff_text, commit_hash, parent_hash).

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    @abstractmethod
    def get_commit_history(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
    ) -> tuple[list[CommitRecord], str | None]:
        """Get the commit history for the workspace branch.

        Returns commits from HEAD back to the fork point (source_git_hash) where
        the workspace was created.

        Args:
            workspace_id: The workspace to get commit history for.
            transaction: Database transaction for atomicity.

        Returns:
            Tuple of (commits, fork_point_hash) where commits is a list of dicts
            with commit metadata and file changes.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
        """

    # Workspace File Operations

    @abstractmethod
    def get_workspace_files(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
    ) -> list[str]:
        """
        List all tracked and untracked file paths in the workspace.

        Returns file paths relative to the workspace root (no directory entries).
        The caller is responsible for inferring directory structure from file paths.

        Args:
            workspace_id: The workspace to list files for.
            transaction: Database transaction for atomicity.

        Returns:
            Sorted list of file paths.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist or environment is not ready.
            WorkspaceFilesUnavailableError: If the underlying git command failed
                (e.g. transient lock contention) and the file list cannot be produced.
        """

    @abstractmethod
    def read_file_at_ref(
        self,
        workspace_id: WorkspaceID,
        file_path: str,
        git_ref: str,
        transaction: DataModelTransaction,
    ) -> FileAtRefResult:
        """
        Read a file's content at a specific git ref.

        Args:
            workspace_id: The workspace containing the file.
            file_path: Relative path to the file within the workspace.
            git_ref: Git ref (branch, tag, commit hash) to read the file at.
            transaction: Database transaction for atomicity.

        Returns:
            The file content with encoding metadata.

        Raises:
            WorkspaceNotFoundError: If the workspace does not exist.
            FileNotFoundAtRefError: If the file does not exist at the given ref.
        """

    # Workspace Artifact Storage
    # Note: workspace_sync_dir is defined as a field by implementations.
    # Workspace artifacts (like DIFF) are stored at:
    # {workspace_sync_dir}/{workspace_id}/{artifact_name}
