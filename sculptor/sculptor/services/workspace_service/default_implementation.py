import base64
import json
import re
import threading
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Generator
from typing import Self
from typing import cast

from loguru import logger
from pydantic import PrivateAttr

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Project
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import DiffStatus
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.foundation.progress_tracking.progress_tracking import start_finish_context
from sculptor.foundation.time_utils import get_current_time
from sculptor.interfaces.agents.agent import EnvironmentTypes

# These artifact types are general-purpose data structures that happen to live under
# interfaces/agents/. They are used by agents, workspace service, and the web layer.
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.interfaces.environments.base import ARTIFACTS_DIRECTORY
from sculptor.interfaces.environments.base import Environment
from sculptor.interfaces.environments.base import TASKS_SUBDIRECTORY
from sculptor.interfaces.environments.errors import EnvironmentConfigurationChangedError
from sculptor.interfaces.environments.errors import EnvironmentNotFoundError
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.data_model_service.data_types import WorkspaceFieldUpdate
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.git_repo_service.git_commands import run_git_command_local
from sculptor.services.git_repo_service.git_errors import GitCommandFailure
from sculptor.services.project_service.api import ProjectService
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.workspace_service.api import CommitFileChange
from sculptor.services.workspace_service.api import CommitRecord
from sculptor.services.workspace_service.api import FileAtRefResult
from sculptor.services.workspace_service.api import FileNotFoundAtRefError
from sculptor.services.workspace_service.api import GitOperationResult
from sculptor.services.workspace_service.api import WorkspaceFilesUnavailableError
from sculptor.services.workspace_service.api import WorkspaceNotFoundError
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.services.workspace_service.api import resolve_workspace_setup_command
from sculptor.services.workspace_service.branch_poller import WorkspaceBranchPoller
from sculptor.services.workspace_service.environment_manager.api import EnvironmentManager
from sculptor.services.workspace_service.environment_manager.default_implementation import DefaultEnvironmentManager
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    stop_all_terminals,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    stop_terminals_for_environment,
)
from sculptor.services.workspace_service.environment_manager.environments.worktree_strategy import remove_worktree
from sculptor.services.workspace_service.setup_command_runner import DefaultSetupStateProvider
from sculptor.services.workspace_service.setup_command_runner import SetupCommandRunner
from sculptor.services.workspace_service.setup_command_runner import SetupStateChanged
from sculptor.services.workspace_service.setup_command_runner import SetupStateProvider
from sculptor.utils.build import build_sculpt_backend_env
from sculptor.utils.build import get_sculpt_bin_dir
from sculptor.utils.timeout import timeout_monitor
from sculptor.utils.type_utils import extract_leaf_types
from sculptor.web.data_types import StreamingUpdateSourceTypes

_ENVIRONMENT_CREATION_TIMEOUT_SECONDS = 60
_DIFF_METADATA_FILENAME = "DIFF.meta.json"
_GIT_COMMAND_TIMEOUT = 30.0

# Number of unchanged context lines shown around each diff hunk by default, and
# the maximum a caller is allowed to request.
_DEFAULT_DIFF_CONTEXT_LINES = 3
_MAX_DIFF_CONTEXT_LINES = 50

# Shell snippet that produces a unified diff for every untracked file.
# Used by both the uncommitted diff and the target-branch diff so that new
# (un-added) files appear in both views.
_UNTRACKED_FILES_DIFF_CMD = (
    "git ls-files --others --exclude-standard -z"
    + " | xargs -0 -I {} find {} -maxdepth 0 -type f -print0"
    + " | xargs -0 -I {} git --no-pager diff --no-index /dev/null {}"
)


class DefaultWorkspaceService(WorkspaceService):
    """
    Default implementation of WorkspaceService.

    This service manages workspace lifecycle and owns the EnvironmentManager
    as an internal implementation detail.
    """

    data_model_service: DataModelService
    dependency_management_service: DependencyManagementService
    environment_manager: EnvironmentManager
    project_service: ProjectService
    workspace_sync_dir: Path
    backend_port: int

    _diff_lock_by_workspace: dict[WorkspaceID, threading.Lock] = PrivateAttr(default_factory=dict)
    _diff_lock_map_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _environment_setup_locks: dict[WorkspaceID, threading.Lock] = PrivateAttr(default_factory=dict)
    _environment_setup_locks_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _setup_runner_instance: SetupCommandRunner | None = PrivateAttr(default=None)
    _setup_runner_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _branch_poller_instance: WorkspaceBranchPoller | None = PrivateAttr(default=None)
    _branch_poller_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    @property
    def setup_runner(self) -> SetupCommandRunner:
        with self._setup_runner_lock:
            if self._setup_runner_instance is None:
                self._setup_runner_instance = SetupCommandRunner(concurrency_group=self.concurrency_group)
            return self._setup_runner_instance

    @property
    def _branch_poller(self) -> WorkspaceBranchPoller:
        """The process-global git-state scanner this service owns.

        Lazily built (like ``setup_runner``) so a single instance is shared by
        every websocket stream that subscribes via ``add_observer``, replacing the
        per-connection pollers. It scans each workspace's current branch and its
        repo's merge-target candidates (keyed by common git dir).
        """
        with self._branch_poller_lock:
            if self._branch_poller_instance is None:
                self._branch_poller_instance = WorkspaceBranchPoller(
                    concurrency_group=self.concurrency_group,
                    data_model_service=self.data_model_service,
                    resolve_working_dir=self.get_workspace_working_directory,
                    refresh_diff_on_branch_change=self.maybe_refresh_workspace_diff,
                )
            return self._branch_poller_instance

    def add_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        self._branch_poller.add_observer(queue)

    def remove_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        self._branch_poller.remove_observer(queue)

    def reconcile_setup_state(self) -> None:
        """Bring persisted setup state into a coherent state on app startup.

        - `running` (interrupted by app exit) → `failed`.
        - `pending` with no project command → `not_configured`.
        - `pending` with a command → leave; `agent_environment_context` will
          kick the runner on first open.
        - Any other status → leave alone.
        """
        with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
            workspaces = list(transaction.get_workspaces())
            projects_by_id: dict[ProjectID, Project] = {p.object_id: p for p in transaction.get_projects()}

        for workspace in workspaces:
            if workspace.is_deleted:
                continue
            project = projects_by_id.get(workspace.project_id)
            if project is None:
                continue
            if workspace.setup_status == "running":
                self.setup_runner.mark_failed_for_reconcile(
                    workspace_id=str(workspace.object_id),
                    started_at=workspace.setup_started_at,
                    on_persist=self._persist_setup_state,
                )
            elif workspace.setup_status == "pending":
                # Honor the project's tri-state default: `None` means use the
                # current default (so we keep `pending` and the runner picks it
                # up on first open), an empty string means the user explicitly
                # cleared it (demote to `not_configured`).
                command = resolve_workspace_setup_command(project.workspace_setup_command)
                if not command:
                    self._persist_setup_state(
                        SetupStateChanged(
                            workspace_id=str(workspace.object_id),
                            status="not_configured",
                            run_id=None,
                            command=None,
                            exit_code=None,
                            started_at=None,
                            finished_at=None,
                            log_truncated=False,
                            log_path=None,
                        )
                    )

    def make_setup_state_provider(self, workspace_id: str) -> SetupStateProvider:
        return DefaultSetupStateProvider(self.setup_runner, workspace_id)

    def _persist_setup_state(self, change: SetupStateChanged) -> None:
        fields: WorkspaceFieldUpdate = {
            "setup_status": change.status,
            "setup_run_id": change.run_id,
            "setup_exit_code": change.exit_code,
            "setup_started_at": change.started_at,
            "setup_finished_at": change.finished_at,
            "setup_log_truncated": change.log_truncated,
            "setup_log_path": change.log_path,
        }
        # Persist the command that was actually run so SetupStatusCard can
        # still display "what ran" if the project's setup_command has since
        # been edited.  Don't overwrite the stored command with None.
        if change.command is not None:
            fields["setup_command"] = change.command
        with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
            transaction.update_workspace_fields(WorkspaceID(change.workspace_id), **fields)

    @classmethod
    def build(
        cls,
        concurrency_group: ConcurrencyGroup,
        settings: SculptorSettings,
        data_model_service: DataModelService,
        project_service: ProjectService,
        dependency_management_service: DependencyManagementService,
    ) -> Self:
        """Build a DefaultWorkspaceService with its internal EnvironmentManager."""
        environment_manager = DefaultEnvironmentManager(
            data_model_service=cast(TaskDataModelService, data_model_service),
        )
        return cls(
            concurrency_group=concurrency_group.make_concurrency_group("workspace_service"),
            data_model_service=data_model_service,
            dependency_management_service=dependency_management_service,
            environment_manager=environment_manager,
            project_service=project_service,
            workspace_sync_dir=settings.workspace_sync_path,
            backend_port=settings.BACKEND_PORT,
        )

    def _get_diff_lock(self, workspace_id: WorkspaceID) -> threading.Lock:
        """Get a per-workspace lock for diff generation, creating one lazily if needed."""
        with self._diff_lock_map_lock:
            if self._diff_lock_by_workspace.get(workspace_id) is None:
                self._diff_lock_by_workspace[workspace_id] = threading.Lock()
        return self._diff_lock_by_workspace[workspace_id]

    def start(self) -> None:
        """Start the workspace service."""
        self._branch_poller.start()

    def stop(self) -> None:
        """Stop the workspace service.

        Stops all active terminals before the ConcurrencyGroup shuts down,
        ensuring pty processes and reader threads are cleanly terminated.
        Also cancels any in-flight setup-command subprocesses and the branch
        scan loop.
        """
        if self._branch_poller_instance is not None:
            self._branch_poller_instance.stop()
        if self._setup_runner_instance is not None:
            self._setup_runner_instance.stop_all()
        stop_all_terminals()

    # Workspace Operations

    def _get_current_git_hash(self, project_path: Path) -> str | None:
        """Get the current HEAD git hash for a project."""
        try:
            returncode, stdout, stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "rev-parse", "HEAD"],
                cwd=project_path,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode == 0:
                return stdout.strip()
            else:
                logger.warning("Failed to get git hash: {}", stderr)
                return None
        except GitCommandFailure as e:
            logger.warning("Failed to get git hash: {}", e)
            return None

    def _resolve_default_target_branch(
        self,
        project_path: Path,
        initialization_strategy: WorkspaceInitializationStrategy,
    ) -> str | None:
        """Detect the best default target branch for a new workspace.

        Checks the user's local repo for a suitable remote-tracking branch to
        use as the diff target.  When no remote-tracking branch is present
        (e.g. a local-only repo with no ``origin``), falls back to the local
        ``main``/``master`` ref:

        * For CLONE workspaces, returns ``origin/<branch>``: clone_strategy
          creates a synthetic ``origin`` remote pointing at the source and
          seeds ``refs/remotes/origin/<branch>`` from the source's local
          branches, so the ref resolves inside the clone.
        * For IN_PLACE and WORKTREE workspaces, returns the bare branch
          name (``main``/``master``): these workspaces share ``.git`` with
          the user's repo, so the local branch resolves directly.
        """
        # Try origin first (most common case)
        branch = self._detect_default_branch_for_remote(project_path, "origin")
        if branch is not None:
            return branch

        if initialization_strategy == WorkspaceInitializationStrategy.CLONE:
            return self._detect_fallback_branch_for_clone_target(project_path)

        return self._detect_local_main_or_master(project_path)

    def _detect_default_branch_for_remote(self, project_path: Path, remote: str) -> str | None:
        """Try to find the default branch for a given remote.

        Resolution order:
        1. ``git symbolic-ref refs/remotes/<remote>/HEAD`` (e.g. ``origin/main``)
        2. ``<remote>/main`` if it exists
        3. ``<remote>/master`` if it exists
        """
        # 1. Try symbolic-ref (set by `git remote set-head --auto`)
        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "symbolic-ref", f"refs/remotes/{remote}/HEAD"],
                cwd=project_path,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode == 0 and stdout.strip():
                # Output is like "refs/remotes/origin/main" → strip to "origin/main"
                full_ref = stdout.strip()
                prefix = "refs/remotes/"
                if full_ref.startswith(prefix):
                    return full_ref[len(prefix) :]
                return full_ref
        except GitCommandFailure:
            pass

        # 2. Check for common default branch names
        for branch_name in ("main", "master"):
            candidate = f"{remote}/{branch_name}"
            try:
                returncode, _stdout, _stderr = run_git_command_local(
                    self.concurrency_group,
                    ["git", "rev-parse", "--verify", f"refs/remotes/{candidate}"],
                    cwd=project_path,
                    check_output=False,
                    timeout=_GIT_COMMAND_TIMEOUT,
                    is_retry_safe=True,
                )
                if returncode == 0:
                    return candidate
            except GitCommandFailure:
                continue

        return None

    def _detect_local_main_or_master(self, project_path: Path) -> str | None:
        """Return the bare local default branch name (``"main"`` or ``"master"``).

        Returns ``None`` if neither local branch exists.
        """
        for branch_name in ("main", "master"):
            try:
                returncode, _stdout, _stderr = run_git_command_local(
                    self.concurrency_group,
                    ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
                    cwd=project_path,
                    check_output=False,
                    timeout=_GIT_COMMAND_TIMEOUT,
                    is_retry_safe=True,
                )
                if returncode == 0:
                    return branch_name
            except GitCommandFailure:
                continue
        return None

    def _detect_fallback_branch_for_clone_target(self, project_path: Path) -> str | None:
        """Return ``origin/main`` or ``origin/master`` for CLONE targets.

        clone_strategy creates a synthetic ``origin`` remote pointing at the
        source path and seeds ``refs/remotes/origin/<branch>`` from the
        source's local branches, so we want the ``origin/<branch>`` form.
        """
        local = self._detect_local_main_or_master(project_path)
        return f"origin/{local}" if local is not None else None

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
        """Create a new workspace for a project."""
        # Generate workspace description if not provided
        if description is None:
            description = uuid.uuid4().hex[:8]

        # Capture the current git hash as the starting point for diffs.
        # source_git_hash can be None if git is not available or HEAD doesn't exist.
        # Diff-generation methods handle None explicitly (see _get_diff_base_ref).
        project_path = project.get_local_user_path()
        source_git_hash = self._get_current_git_hash(project_path)

        # Use the caller-provided target branch if given, otherwise resolve a
        # sensible default from the user's repo.
        if target_branch is None:
            target_branch = self._resolve_default_target_branch(project_path, initialization_strategy)

        # Resolve through the project's tri-state default helper: `None` means
        # "use the current default", `""` means "user cleared", and any other
        # value is the user's custom command. Setup runs on any fresh isolated
        # checkout — both CLONE and WORKTREE.
        resolved_setup_command = resolve_workspace_setup_command(project.workspace_setup_command)
        has_command = resolved_setup_command is not None and resolved_setup_command != ""
        is_clone_or_worktree = initialization_strategy in (
            WorkspaceInitializationStrategy.CLONE,
            WorkspaceInitializationStrategy.WORKTREE,
        )
        initial_setup_status = "pending" if (has_command and is_clone_or_worktree) else "not_configured"

        workspace_id = WorkspaceID()
        workspace = Workspace(
            object_id=workspace_id,
            project_id=project.object_id,
            organization_reference=project.organization_reference,
            description=description,
            initialization_strategy=initialization_strategy,
            source_branch=source_branch,
            requested_branch_name=requested_branch_name,
            source_git_hash=source_git_hash,
            target_branch=target_branch,
            setup_status=initial_setup_status,
        )

        logger.debug(
            "Creating workspace {} for project {} with source_git_hash={}, target_branch={}",
            workspace.object_id,
            project.object_id,
            source_git_hash,
            target_branch,
        )
        created_workspace = transaction.upsert_workspace(workspace)

        return created_workspace

    def update_workspace(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
        description: str | None = None,
        target_branch: str | None = None,
        is_open: bool | None = None,
    ) -> Workspace:
        """Update a workspace's description, target branch, and/or open state."""
        fields: WorkspaceFieldUpdate = {}
        if description is not None:
            fields["description"] = description
        if target_branch is not None:
            fields["target_branch"] = target_branch
        if is_open is not None:
            fields["is_open"] = is_open
        if not fields:
            # update_workspace_fields requires at least one field; fall
            # back to fetch-and-return for the no-op call.
            workspace = transaction.get_workspace(workspace_id)
            if workspace is None or workspace.is_deleted:
                raise WorkspaceNotFoundError(workspace_id)
            return workspace
        updated_workspace = transaction.update_workspace_fields(workspace_id, **fields)
        if updated_workspace is None:
            raise WorkspaceNotFoundError(workspace_id)
        logger.debug("Updated workspace {}", workspace_id)
        return updated_workspace

    def delete_workspace(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
    ) -> None:
        """Delete a workspace and its associated environment.

        The environment (filesystem) is deleted in a post-commit callback so that
        the directory is only removed after the transaction successfully commits.
        This avoids leaving the DB with is_deleted=False when the directory is already gone.
        """
        workspace = transaction.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        updated_workspace = workspace.evolve(workspace.ref().is_deleted, True)
        transaction.upsert_workspace(updated_workspace)
        logger.debug("Soft-deleted workspace {}", workspace_id)

        # Delete the environment after the transaction commits so filesystem
        # stays in sync with the database.
        if workspace.environment_id is not None:
            environment_id = workspace.environment_id
            environment_manager = self.environment_manager
            initialization_strategy = workspace.initialization_strategy
            requested_branch_name = workspace.requested_branch_name
            project = transaction.get_project(workspace.project_id)
            concurrency_group = self.concurrency_group

            setup_runner = self.setup_runner

            def _delete_environment() -> None:
                # Stop all terminals (all tab indices) first, before any of the
                # directory teardown below.  A terminal's child process uses the
                # `<environment_id>/code` worktree checkout as its working
                # directory; removing that directory (via remove_worktree or the
                # rmtree in delete_environment) out from under a live process is
                # what causes the messy "Electron quit unexpectedly" shutdown in
                # SCU-1424.  Without an active agent, destroy() won't be called,
                # so we must stop terminals here both to avoid orphaned PTY
                # processes and to let them exit cleanly while their working
                # directory still exists.
                stop_terminals_for_environment(environment_id)
                # Cancel any in-flight setup-command subprocess before the
                # environment directory is removed.
                setup_runner.cancel(str(workspace_id))
                # For WORKTREE workspaces, run `git worktree remove` in the user's
                # repo before rmtree so the gitfile entry is cleaned up and the
                # tri-state branch deletion policy is applied.
                if initialization_strategy == WorkspaceInitializationStrategy.WORKTREE:
                    if project is not None and requested_branch_name is not None:
                        user_config = get_user_config_instance()
                        deletion_policy = (
                            user_config.workspace_branch_deletion_policy
                            if user_config is not None
                            else "delete_if_safe"
                        )
                        try:
                            # The worktree checkout lives at `<environment_id>/code/`,
                            # not at `<environment_id>` itself (which is the workspace dir
                            # containing state/, artifacts/, and code/).
                            remove_worktree(
                                user_repo_path=project.get_local_user_path(),
                                destination=Path(environment_id) / "code",
                                branch_name=requested_branch_name,
                                deletion_policy=deletion_policy,
                                concurrency_group=concurrency_group,
                            )
                        except Exception as e:
                            logger.info("Failed to remove worktree for workspace {}: {}", workspace_id, e)
                    else:
                        logger.info(
                            "Skipping worktree removal for workspace {} (project={}, branch={})",
                            workspace_id,
                            project,
                            requested_branch_name,
                        )
                environment_manager.delete_environment(environment_id)
                logger.info("Deleted environment {} for workspace {}", environment_id, workspace_id)

            # Run the slow teardown (worktree removal + shutil.rmtree of the whole
            # workspace directory + terminal shutdown) on a background thread rather
            # than the request thread.  The rmtree can take many seconds for a real
            # workspace, and running it inline in the post-commit hook holds the
            # DELETE request's server worker thread for that whole time; deleting
            # several workspaces in quick succession then exhausts the connection
            # limit and the app starts dropping requests (SCU-1374).  The soft-delete
            # is already committed above, and cleanup_stale_environments() removes
            # the directory on the next startup if the app exits before this finishes.
            transaction.add_callback(
                lambda: concurrency_group.start_new_thread(
                    target=_delete_environment,
                    name=f"delete-environment-{workspace_id}",
                    is_checked=False,
                )
            )

    # Environment Lifecycle

    @contextmanager
    def _environment_setup_lock(self, workspace_id: WorkspaceID) -> Generator[None, None, None]:
        """Per-workspace lock for environment setup.

        This prevents two tasks in the same workspace from racing to create
        duplicate environments when both resume simultaneously (e.g. after
        application restart).
        """
        with self._environment_setup_locks_lock:
            if workspace_id not in self._environment_setup_locks:
                self._environment_setup_locks[workspace_id] = threading.Lock()
            lock = self._environment_setup_locks[workspace_id]
        with lock:
            yield

    def _create_or_resume_environment(
        self,
        project: Project,
        workspace_id: WorkspaceID,
        concurrency_group: ConcurrencyGroup,
        root_progress_handle: RootProgressHandle,
        task_id: str,
    ) -> EnvironmentTypes:
        """Create or resume the environment for a workspace, protected by a per-workspace lock.

        The lock ensures that concurrent tasks in the same workspace don't create
        duplicate environments.
        """
        project_path = project.get_local_user_path()

        with self._environment_setup_lock(workspace_id):
            # Read workspace inside the lock to see updates from other threads
            with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                workspace = transaction.get_workspace(workspace_id)

            if workspace is None:
                raise WorkspaceNotFoundError(workspace_id)

            environment_id_to_resume = workspace.environment_id
            environment: Environment | None = None

            user_config = get_user_config_instance()
            env_var_override = user_config.env_var_override_enabled if user_config is not None else False

            try:
                if environment_id_to_resume is None:
                    raise EnvironmentNotFoundError()

                environment = self.environment_manager.resume_environment(
                    environment_id=environment_id_to_resume,
                    project_path=project_path,
                    project_id=project.object_id,
                    concurrency_group=concurrency_group,
                    initialization_strategy=workspace.initialization_strategy,
                    env_var_override=env_var_override,
                )
                logger.debug(
                    "Resumed existing environment {} for workspace {}", environment_id_to_resume, workspace_id
                )
            except (EnvironmentNotFoundError, EnvironmentConfigurationChangedError) as e:
                logger.debug("Unable to resume environment: {}", e)

                with (
                    timeout_monitor(
                        concurrency_group,
                        timeout=_ENVIRONMENT_CREATION_TIMEOUT_SECONDS,
                        on_timeout=lambda timeout: logger.warning(
                            "Environment creation is taking longer than expected ({}s) for workspace {}",
                            timeout,
                            workspace_id,
                        ),
                    ),
                    start_finish_context(
                        root_progress_handle.track_environment_setup(task_id)
                    ) as environment_setup_handle,  # noqa: F841
                ):
                    environment = self.environment_manager.create_environment(
                        project_path=project_path,
                        project_id=project.object_id,
                        concurrency_group=concurrency_group,
                        initialization_strategy=workspace.initialization_strategy,
                        source_branch=workspace.source_branch,
                        requested_branch_name=workspace.requested_branch_name,
                        env_var_override=env_var_override,
                    )
                logger.debug("Created new environment {} for workspace {}", environment.environment_id, workspace_id)

            # Type narrowing for pycharm/the type checker
            assert isinstance(environment, extract_leaf_types(EnvironmentTypes))
            environment = cast(EnvironmentTypes, environment)

            # Expose sculpt CLI env vars in the terminal so bare `sculpt` invocations
            # can reach the backend and resolve the workspace/project without flags.
            # Set on the concrete type — this is a workspace-level concern
            # that doesn't belong in the EnvironmentManager interface.
            environment.set_sculpt_terminal_env_vars(
                {
                    **build_sculpt_backend_env(
                        backend_port=self.backend_port,
                        workspace_id=workspace_id,
                        project_id=project.object_id,
                    ),
                    "PATH": str(get_sculpt_bin_dir()),
                }
            )

            if workspace.environment_id != environment.environment_id:
                with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                    transaction.update_workspace_fields(workspace.object_id, environment_id=environment.environment_id)
                logger.debug(
                    "Updated workspace {} with environment_id {}", workspace.object_id, environment.environment_id
                )

            return environment

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
        """Set up the environment for a workspace and wrap it for agent use."""
        environment = self._create_or_resume_environment(
            project=project,
            workspace_id=workspace_id,
            concurrency_group=concurrency_group,
            root_progress_handle=root_progress_handle,
            task_id=str(task_id),
        )

        # Wrap the environment in AgentExecutionEnvironment for per-task namespacing
        agent_environment = LocalAgentExecutionEnvironment(
            environment, task_id, dependency_management_service=self.dependency_management_service
        )
        logger.debug(
            "Created AgentExecutionEnvironment for task {} with state_path={}",
            task_id,
            agent_environment.get_state_path(),
        )

        # Start the terminal at the workspace/environment level, not per-agent.
        # This is idempotent — if a terminal is already running (from a previous agent
        # run or a concurrent agent), it will be reused.
        # Uses the workspace_service concurrency group (server-lifetime) so the terminal
        # outlives individual agent runs.
        # Wrapped in try/except so terminal failure doesn't prevent workspace startup.
        # The terminal will be created on demand when the user first connects.
        if environment.supports_terminal:
            try:
                environment.start_terminal_manager(self.concurrency_group)
            except Exception as e:
                logger.error(
                    "Failed to start terminal for workspace {}, terminal will be created on demand: {}",
                    workspace_id,
                    e,
                )

        # Kick off the workspace setup command via the SetupCommandRunner if the
        # workspace is in the `pending` state. This is gated on the persisted
        # setup_status (set at workspace creation time) so the toggle and the
        # project setup command have already been resolved.
        # Read setup_status outside of the runner.start call so the immediate
        # transaction is closed before the runner's on_persist callback opens
        # its own transaction (otherwise SQLite locks).
        should_start_setup = False
        setup_command_to_run: str | None = None
        try:
            with self.data_model_service.open_transaction(request_id=RequestID(), immediate=True) as transaction:
                workspace = transaction.get_workspace(workspace_id)
                # Resolve the project's tri-state setup command: `None` means
                # "use the current default", `""` means "user cleared, run nothing",
                # and any other value is the user's custom command.
                setup_command_to_run = resolve_workspace_setup_command(project.workspace_setup_command)
                if (
                    workspace is not None
                    and workspace.setup_status == "pending"
                    and setup_command_to_run
                    and self.setup_runner.get_state(str(workspace_id)) is None
                ):
                    should_start_setup = True
        except Exception as e:
            logger.error("Failed to read workspace setup status for {}: {}", workspace_id, e)

        if should_start_setup and setup_command_to_run:
            try:
                state_dir = environment.to_host_path(environment.get_state_path())
                self.setup_runner.start(
                    workspace_id=str(workspace_id),
                    command=setup_command_to_run,
                    subprocess_runner=environment.run_setup_subprocess,
                    shutdown_event_source=environment.concurrency_group.shutdown_event,
                    state_dir=state_dir,
                    on_persist=self._persist_setup_state,
                )
            except Exception as e:
                logger.error("Failed to kick off workspace setup for {}: {}", workspace_id, e)

        # Write task ID to per-task state directory for debugging
        agent_environment.write_file(str(agent_environment.get_state_path() / "sculptor_task_id.txt"), str(task_id))

        try:
            with logger.contextualize(environment=environment.get_extra_logger_context()):
                logger.debug("AgentExecutionEnvironment ready for task {} in workspace {}", task_id, workspace_id)
                yield agent_environment
        finally:
            should_destroy = False
            should_cleanup_environments = False
            with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                updated_workspace = transaction.get_workspace(workspace_id)
                if updated_workspace is not None:
                    # Check if workspace's environment_id changed (workspace is the single owner of environment)
                    if updated_workspace.environment_id != environment.environment_id:
                        should_destroy = True
                    if updated_workspace.is_deleted:
                        should_destroy = True
                        should_cleanup_environments = True
            environment.close()
            # If the workspace is no longer tied to this environment, there's no reason to keep it around
            if should_destroy:
                environment.destroy()

            if should_cleanup_environments:
                self.environment_manager.cleanup_stale_environments()

    # Workspace Diff Operations

    def _get_workspace_artifact_dir(self, workspace_id: WorkspaceID) -> Path:
        """Get the directory for storing workspace artifacts."""
        return self.workspace_sync_dir / str(workspace_id)

    def get_persistent_task_artifacts_dir(
        self,
        workspace_id: WorkspaceID,
        task_id: TaskID,
    ) -> Path | None:
        with self.data_model_service.open_transaction(request_id=RequestID()) as txn:
            workspace = txn.get_workspace(workspace_id)
        if workspace is None or workspace.environment_id is None:
            return None
        return Path(workspace.environment_id) / ARTIFACTS_DIRECTORY / TASKS_SUBDIRECTORY / str(task_id)

    def get_workspace_working_directory(
        self,
        workspace: Workspace,
        transaction: DataModelTransaction | None = None,
    ) -> Path | None:
        """Get the git working directory for a workspace.

        Delegates to the Environment abstraction so IN_PLACE vs CLONE path logic
        lives in one place (LocalEnvironment.get_working_directory).

        Returns None if the workspace's environment hasn't been initialized yet.
        """
        if transaction is not None:
            project = transaction.get_project(workspace.project_id)
        else:
            with self.data_model_service.open_transaction(request_id=RequestID()) as txn:
                project = txn.get_project(workspace.project_id)
        if project is None:
            raise WorkspaceNotFoundError(workspace.object_id)

        if workspace.environment_id is None:
            if workspace.initialization_strategy == WorkspaceInitializationStrategy.IN_PLACE:
                return project.get_local_user_path()
            return None

        environment = self.environment_manager.resume_environment(
            environment_id=workspace.environment_id,
            project_path=project.get_local_user_path(),
            project_id=project.object_id,
            concurrency_group=self.concurrency_group,
            initialization_strategy=workspace.initialization_strategy,
        )
        return environment.get_working_directory()

    def _get_workspace_working_dir(
        self,
        workspace: Workspace,
        transaction: DataModelTransaction,
    ) -> Path:
        """Get the working directory for a workspace (where git operations run)."""
        working_dir = self.get_workspace_working_directory(workspace, transaction)
        if working_dir is None:
            raise WorkspaceNotFoundError(workspace.object_id)
        return working_dir

    def _run_diff_command(
        self,
        command: list[str],
        cwd: Path,
        diff_kind: str,
    ) -> str:
        """Run a git diff command and return its output.

        Args:
            command: The git command to run.
            cwd: Working directory for the command.
            diff_kind: Human-readable label for the diff type (e.g. "committed", "uncommitted").

        Returns:
            The diff output, or empty string on failure.
        """
        try:
            returncode, stdout, stderr = run_git_command_local(
                self.concurrency_group,
                command,
                cwd=cwd,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            # returncode 0 = empty diff, 1 = non-empty diff, >1 = error
            # 123 = xargs found items (which is fine for our use case)
            if returncode > 1 and returncode != 123:
                logger.warning(
                    "Unexpected returncode for {} diff: returncode={}, stderr={}",
                    diff_kind,
                    returncode,
                    stderr[:500],
                )
            return stdout.strip()
        except GitCommandFailure as e:
            logger.warning("Failed to generate {} diff: {}", diff_kind, e)
            return ""

    def _create_diff_artifact_local(
        self,
        base_ref: str,
        working_dir: Path,
        context_lines: int = _DEFAULT_DIFF_CONTEXT_LINES,
        target_branch: str | None = None,
    ) -> DiffArtifact:
        """Create a diff artifact using local git commands.

        Args:
            base_ref: Git ref to diff against (branch name, commit hash, or "HEAD~0").
            working_dir: Working directory for git commands.
            context_lines: Number of unchanged context lines around each diff hunk.
            target_branch: If set, compute target-branch diff using merge-base.
        """
        if not isinstance(context_lines, int) or context_lines < 0:
            raise ValueError(f"context_lines must be a non-negative integer, got {context_lines!r}")
        context_flag = f"-U{context_lines}"

        # Commands to generate each diff type.
        # -M enables rename detection so renames show as a single entry instead of delete+add.
        untracked = _UNTRACKED_FILES_DIFF_CMD
        uncommitted_diff_command = [
            "bash",
            "-c",
            f"git --no-pager diff -M {context_flag} HEAD; {untracked}",
        ]
        uncommitted_diff = self._run_diff_command(uncommitted_diff_command, working_dir, "uncommitted")

        # Compute target-branch diff if requested.  Resolve the merge-base once
        # and reuse it both to compute the diff and to expose it on the artifact,
        # so the frontend can fetch old-side file content at the exact ref the
        # diff's old-side line numbers reference (rather than the target-branch
        # tip, which may have diverged since the merge-base).
        target_branch_diff = ""
        target_branch_merge_base = ""
        if target_branch is not None:
            merge_base = self._get_merge_base(working_dir, target_branch)
            if merge_base is not None:
                target_branch_merge_base = merge_base
                target_branch_diff = self._compute_target_branch_diff(working_dir, merge_base, context_flag)

        # Detect per-file errors (e.g., files inside nested git repositories)
        file_errors = self._detect_file_errors(working_dir)

        return DiffArtifact(
            uncommitted_diff=uncommitted_diff,
            target_branch_diff=target_branch_diff,
            target_branch_merge_base=target_branch_merge_base,
            file_errors=file_errors,
        )

    def _get_merge_base(self, working_dir: Path, target_branch: str) -> str | None:
        """Return the merge-base of HEAD and *target_branch*, or ``None`` on failure."""
        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "merge-base", "HEAD", target_branch],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode != 0 or not stdout.strip():
                return None
            return stdout.strip()
        except GitCommandFailure:
            return None

    def _compute_target_branch_diff(
        self,
        working_dir: Path,
        merge_base: str,
        context_flag: str,
    ) -> str:
        """Compute the diff from the given merge-base commit to the working tree.

        This includes both committed and uncommitted changes so the "All changes"
        view reflects the full delta against the target branch. The caller
        resolves the merge-base (so the exact same commit can be exposed on the
        artifact for the frontend's old-side content fetch).
        """
        # Diff merge-base against the working tree (not HEAD) so uncommitted
        # changes are included.  Also append untracked files, matching the
        # approach used for the uncommitted diff.
        untracked = _UNTRACKED_FILES_DIFF_CMD
        diff_command = [
            "bash",
            "-c",
            f"git --no-pager diff -M {context_flag} {merge_base}; {untracked}",
        ]
        return self._run_diff_command(diff_command, working_dir, "target-branch")

    def _detect_file_errors(self, working_dir: Path) -> dict[str, str]:
        """Detect files that cannot be diffed (e.g., inside nested git repos)."""
        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode != 0:
                return {}
        except GitCommandFailure:
            return {}

        file_paths = [f for f in stdout.split("\0") if f.strip()]
        errors: dict[str, str] = {}
        for file_path in file_paths:
            if "/.git/" in f"/{file_path}/" and not file_path.startswith(".git/"):
                errors[file_path] = "Could not generate diff: file is inside a nested git repository"

        return errors

    @staticmethod
    def _get_diff_base_ref(workspace: Workspace) -> str:
        """Get the git ref to use as the diff baseline for a workspace.

        If source_branch is set, diff against that branch (e.g., "main").
        Otherwise, diff from the captured source_git_hash.
        Falls back to HEAD~0 (empty diff) if neither is available.
        """
        if workspace.source_branch is not None:
            return workspace.source_branch
        if workspace.source_git_hash is not None:
            return workspace.source_git_hash
        return "HEAD~0"

    def refresh_workspace_diff(
        self,
        workspace_id: WorkspaceID,
        context_lines: int | None = None,
        include_target_branch_diff: bool = False,
    ) -> None:
        """Regenerate workspace diff and store it.

        Acquires a per-workspace lock (non-blocking) to prevent concurrent generation.
        Manages its own transactions for each status transition so the frontend sees
        GENERATING and READY states as they happen.
        """
        lock = self._get_diff_lock(workspace_id)
        if not lock.acquire(blocking=False):
            logger.debug("Diff generation already in progress for workspace {}, skipping", workspace_id)
            return

        # Honor an explicit context_lines=0 (zero context); only None means "use
        # the default". Clamp the result into the supported range.
        context_lines_or_default = _DEFAULT_DIFF_CONTEXT_LINES if context_lines is None else context_lines
        effective_context_lines = min(max(context_lines_or_default, 0), _MAX_DIFF_CONTEXT_LINES)

        try:
            # Capture timestamp at the start for staleness detection: if the repo
            # changes during generation, diff_updated_at will be older than the
            # latest modification, signalling that the diff may be stale.
            generated_at = get_current_time()

            with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                workspace = transaction.update_workspace_fields(workspace_id, diff_status=DiffStatus.GENERATING)
                if workspace is None:
                    raise WorkspaceNotFoundError(workspace_id)

                base_ref = self._get_diff_base_ref(workspace)
                working_dir = self._get_workspace_working_dir(workspace, transaction)
                target_branch = workspace.target_branch if include_target_branch_diff else None

            # Generate the diff artifact (outside transaction — may be slow)
            diff_artifact = self._create_diff_artifact_local(
                base_ref, working_dir, effective_context_lines, target_branch=target_branch
            )

            # Store the artifact to disk
            artifact_dir = self._get_workspace_artifact_dir(workspace_id)
            artifact_dir.mkdir(parents=True, exist_ok=True)

            artifact_path = artifact_dir / ArtifactType.DIFF
            artifact_path.write_text(diff_artifact.model_dump_json(indent=2))

            metadata = {"generated_at": generated_at.isoformat()}
            metadata_path = artifact_dir / _DIFF_METADATA_FILENAME
            metadata_path.write_text(json.dumps(metadata))

            logger.debug(
                "Refreshed workspace diff for {} at {}",
                workspace_id,
                artifact_path,
            )

            with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                updated = transaction.update_workspace_fields(
                    workspace_id, diff_status=DiffStatus.READY, diff_updated_at=generated_at
                )
                if updated is None:
                    logger.debug(
                        "Workspace {} was deleted during diff generation, skipping READY update", workspace_id
                    )
                    return

        except Exception:
            # Reset diff_status to NONE so the frontend knows generation failed.
            try:
                with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                    transaction.update_workspace_fields(workspace_id, diff_status=DiffStatus.NONE)
            except Exception:
                logger.warning("Failed to reset diff_status for workspace {}", workspace_id)
            raise
        finally:
            lock.release()

    def maybe_refresh_workspace_diff(
        self,
        workspace_id: WorkspaceID,
    ) -> None:
        """Regenerate workspace diff if needed. For now, always refreshes."""
        # Future: could check if files actually changed before regenerating
        # For now, always refresh.  Always include the target-branch diff so the
        # frontend "All changes" view stays up-to-date without extra requests.
        self.refresh_workspace_diff(workspace_id, include_target_branch_diff=True)

    def mark_workspace_diff_stale(
        self,
        workspace_id: WorkspaceID,
    ) -> None:
        """Signal the frontend that a diff is available without generating it.

        Sets diff_status=READY and diff_updated_at=now() so the frontend fetches
        the diff via GET /workspaces/{id}/diff, which generates on-demand.
        """
        now = get_current_time()
        with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
            updated = transaction.update_workspace_fields(
                workspace_id, diff_status=DiffStatus.READY, diff_updated_at=now
            )
            if updated is None:
                raise WorkspaceNotFoundError(workspace_id)

    def get_workspace_diff(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
        force_refresh: bool = False,
        context_lines: int | None = None,
        include_target_branch_diff: bool = False,
    ) -> DiffArtifact | None:
        """Get the latest stored diff artifact for the workspace.

        If no artifact exists on disk, generates one on-demand. This supports
        lazy diff generation where agent startup marks the diff as READY without
        actually generating the artifact.
        """
        workspace = transaction.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        if force_refresh:
            self.refresh_workspace_diff(
                workspace_id,
                context_lines=context_lines,
                include_target_branch_diff=include_target_branch_diff,
            )

        artifact_dir = self._get_workspace_artifact_dir(workspace_id)
        artifact_path = artifact_dir / ArtifactType.DIFF

        if not artifact_path.exists():
            # Artifact missing — generate on-demand (lazy diff from startup).
            self.refresh_workspace_diff(workspace_id, context_lines=context_lines)

        if not artifact_path.exists():
            return None

        try:
            artifact_data = artifact_path.read_text()
            return DiffArtifact.model_validate_json(artifact_data)
        except Exception as e:
            logger.warning("Failed to read diff artifact for {}: {}", workspace_id, e)
            return None

    # Workspace Git Operations

    def discard_file(
        self,
        workspace_id: WorkspaceID,
        file_path: str,
        transaction: DataModelTransaction,
    ) -> GitOperationResult:
        """Discard changes to a single file in the workspace."""
        workspace = transaction.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        working_dir = self._get_workspace_working_dir(workspace, transaction)

        # Path validation: reject path traversal and absolute paths
        validation_error = self._validate_file_path(file_path, working_dir)
        if validation_error is not None:
            return GitOperationResult(
                success=False,
                stdout="",
                stderr="",
                error_message=validation_error,
            )

        # Check if the file is tracked
        is_tracked = self._is_file_tracked(file_path, working_dir)

        if is_tracked:
            command = ["git", "checkout", "HEAD", "--", file_path]
        else:
            command = ["git", "clean", "-f", "--", file_path]

        try:
            returncode, stdout, stderr = run_git_command_local(
                self.concurrency_group,
                command,
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=False,
            )

            success = returncode == 0
            error_message = None if success else f"Git command failed with exit code {returncode}"

            result = GitOperationResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                error_message=error_message,
            )

            self.maybe_refresh_workspace_diff(workspace_id)
            return result

        except GitCommandFailure as e:
            self.maybe_refresh_workspace_diff(workspace_id)
            return GitOperationResult(
                success=False,
                stdout=e.stdout,
                stderr=e.stderr,
                error_message=str(e),
            )

    @staticmethod
    def _validate_file_path(file_path: str, working_dir: Path) -> str | None:
        """Validate a file path is safe and within the workspace. Returns error message or None."""
        if file_path.startswith("/"):
            return "Absolute paths are not allowed"

        # Check for path traversal via .. components
        resolved = (working_dir / file_path).resolve()
        if not resolved.is_relative_to(working_dir.resolve()):
            return "Path traversal is not allowed"

        return None

    def _is_file_tracked(self, file_path: str, working_dir: Path) -> bool:
        """Check if a file is tracked by git."""
        try:
            returncode, _stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "ls-files", "--error-unmatch", file_path],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            return returncode == 0
        except GitCommandFailure:
            return False

    _COMMIT_HASH_PATTERN = re.compile(r"^[0-9a-f]{4,40}$")

    def get_commit_diff(
        self,
        workspace_id: WorkspaceID,
        commit_hash: str,
        transaction: DataModelTransaction,
    ) -> tuple[str, str, str | None]:
        """Get the unified diff for a single commit."""
        workspace = transaction.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        working_dir = self._get_workspace_working_dir(workspace, transaction)

        # Validate commit hash format
        if not self._COMMIT_HASH_PATTERN.match(commit_hash):
            raise ValueError(f"Invalid commit hash: {commit_hash}")

        # Validate it's actually a commit object and resolve to full hash
        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "cat-file", "-t", commit_hash],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode != 0 or stdout.strip() != "commit":
                raise ValueError(f"Not a valid commit: {commit_hash}")
        except GitCommandFailure as e:
            raise ValueError(f"Not a valid commit: {commit_hash}") from e

        # Resolve to full hash so callers always get a canonical 40-char SHA
        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "rev-parse", commit_hash],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode == 0 and stdout.strip():
                commit_hash = stdout.strip()
        except GitCommandFailure:
            pass

        # Try to get parent hash
        parent_hash: str | None = None
        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "rev-parse", f"{commit_hash}^"],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode == 0 and stdout.strip():
                parent_hash = stdout.strip()
        except GitCommandFailure:
            pass

        # Generate the diff
        if parent_hash is not None:
            diff_command = ["git", "--no-pager", "diff", "-M", f"{parent_hash}..{commit_hash}"]
        else:
            # Root commit — no parent
            diff_command = ["git", "--no-pager", "diff-tree", "-p", "--root", "-M", commit_hash]

        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                diff_command,
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
            diff_text = stdout if returncode <= 1 else ""
        except GitCommandFailure:
            diff_text = ""

        return (diff_text, commit_hash, parent_hash)

    _MAX_COMMITS = 500

    def get_commit_history(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
    ) -> tuple[list[CommitRecord], str | None]:
        """Get the commit history for the workspace branch."""
        workspace = transaction.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        working_dir = self._get_workspace_working_dir(workspace, transaction)

        # Determine fork point
        fork_point = self._resolve_fork_point(workspace, working_dir)
        if fork_point is None:
            return ([], None)

        # Get commit metadata (using unit separator \x1f to avoid collisions)
        separator = "\x1f"
        format_str = f"%H{separator}%h{separator}%s{separator}%aN{separator}%aE{separator}%aI{separator}%P"
        try:
            returncode, stdout, stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "log", f"-n{self._MAX_COMMITS}", f"--format={format_str}", f"{fork_point}..HEAD"],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
        except GitCommandFailure:
            return ([], fork_point)

        if returncode != 0 or not stdout.strip():
            return ([], fork_point)

        # Parse commit metadata
        commit_meta: list[dict] = []
        for line in stdout.strip().split("\n"):
            parts = line.split(separator)
            if len(parts) != 7:
                continue
            parent_hashes = parts[6].split() if parts[6] else []
            commit_meta.append(
                {
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "message": parts[2],
                    "author_name": parts[3],
                    "author_email": parts[4],
                    "timestamp": parts[5],
                    "parent_hashes": parent_hashes,
                }
            )

        if not commit_meta:
            return ([], fork_point)

        # Get file stats (numstat) for all commits in one command
        numstat_by_hash = self._parse_log_file_data(working_dir, fork_point, "--numstat", self._parse_numstat_lines)

        # Get file statuses (name-status) for all commits in one command
        status_by_hash = self._parse_log_file_data(
            working_dir, fork_point, "--name-status", self._parse_name_status_lines
        )

        # Combine into final commit list
        commits: list[CommitRecord] = []
        for meta in commit_meta:
            commit_hash = meta["hash"]
            numstat = numstat_by_hash.get(commit_hash, {})
            statuses = status_by_hash.get(commit_hash, {})

            files = []
            all_paths = set(numstat.keys()) | set(statuses.keys())
            for path in sorted(all_paths):
                stats = numstat.get(path, (0, 0))
                status_info = statuses.get(path, ("M", None))
                files.append(
                    CommitFileChange(
                        path=path,
                        status=status_info[0],
                        old_path=status_info[1],
                        additions=stats[0],
                        deletions=stats[1],
                    )
                )

            commits.append(
                CommitRecord(
                    hash=meta["hash"],
                    short_hash=meta["short_hash"],
                    message=meta["message"],
                    author_name=meta["author_name"],
                    author_email=meta["author_email"],
                    timestamp=meta["timestamp"],
                    parent_hashes=meta["parent_hashes"],
                    files=files,
                )
            )

        return (commits, fork_point)

    def _resolve_fork_point(self, workspace: Workspace, working_dir: Path) -> str | None:
        """Determine the fork point hash for commit history.

        Uses ``git merge-base HEAD <target_branch>`` so the history correctly
        excludes commits reachable from the target branch — even after merges
        or rebases that move the common ancestor forward.  Falls back to
        ``source_git_hash`` when no target branch is configured or when the
        merge-base command fails.
        """
        target_branch = workspace.target_branch
        if target_branch is None:
            return workspace.source_git_hash

        return self._get_merge_base(working_dir, target_branch) or workspace.source_git_hash

    def _parse_log_file_data(
        self,
        working_dir: Path,
        fork_point: str,
        flag: str,
        parser: "Callable[[list[str]], dict]",
    ) -> dict[str, dict]:
        """Run git log with a file-data flag and parse results by commit hash."""
        try:
            returncode, stdout, _stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "log", f"-n{self._MAX_COMMITS}", "--format=COMMIT_SEP:%H", flag, "-M", f"{fork_point}..HEAD"],
                cwd=working_dir,
                check_output=False,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
            )
        except GitCommandFailure:
            return {}

        if returncode != 0 or not stdout.strip():
            return {}

        result: dict[str, dict] = {}
        current_hash = None
        current_lines: list[str] = []

        for line in stdout.split("\n"):
            if line.startswith("COMMIT_SEP:"):
                if current_hash is not None:
                    result[current_hash] = parser(current_lines)
                current_hash = line[len("COMMIT_SEP:") :]
                current_lines = []
            elif line.strip():
                current_lines.append(line)

        if current_hash is not None:
            result[current_hash] = parser(current_lines)

        return result

    @staticmethod
    def _expand_numstat_rename_path(path: str) -> str:
        """Expand git's compact rename notation into the new path.

        git log --numstat -M uses compact notation for renames:
        - ``{old => new}/file.py`` → ``new/file.py``
        - ``prefix/{old => new}/file.py`` → ``prefix/new/file.py``
        - ``old.py => new.py`` → ``new.py``
        - ``{ => new}/file.py`` → ``new/file.py``
        - ``{old => }/file.py`` → ``file.py``
        """
        # Brace notation: {old => new}
        brace_start = path.find("{")
        if brace_start != -1:
            brace_end = path.find("}", brace_start)
            arrow = path.find(" => ", brace_start)
            if brace_end != -1 and arrow != -1 and arrow < brace_end:
                prefix = path[:brace_start]
                new_part = path[arrow + 4 : brace_end]
                suffix = path[brace_end + 1 :]
                result = prefix + new_part + suffix
                return result.lstrip("/")

        # Simple rename: old => new
        arrow = path.find(" => ")
        if arrow != -1:
            return path[arrow + 4 :]

        return path

    @staticmethod
    def _parse_numstat_lines(lines: list[str]) -> dict[str, tuple[int, int]]:
        """Parse numstat lines into {path: (additions, deletions)}."""
        result: dict[str, tuple[int, int]] = {}
        for line in lines:
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            add_str, del_str = parts[0], parts[1]
            # Binary files show as "-\t-\tpath"
            additions = 0 if add_str == "-" else int(add_str)
            deletions = 0 if del_str == "-" else int(del_str)
            # Renames show as "old_path\tnew_path" in the path portion
            if len(parts) == 4:
                # Rename: additions\tdeletions\told_path\tnew_path
                path = parts[3]
            else:
                path = parts[2]
            # Expand compact rename notation ({old => new}/file) to the new path
            if "=>" in path:
                path = DefaultWorkspaceService._expand_numstat_rename_path(path)
            result[path] = (additions, deletions)
        return result

    @staticmethod
    def _parse_name_status_lines(lines: list[str]) -> dict[str, tuple[str, str | None]]:
        """Parse name-status lines into {path: (status, old_path)}."""
        result: dict[str, tuple[str, str | None]] = {}
        for line in lines:
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status = parts[0]
            if status.startswith("R"):
                # Rename: R100\told_path\tnew_path
                if len(parts) >= 3:
                    old_path = parts[1]
                    new_path = parts[2]
                    result[new_path] = ("R", old_path)
            else:
                # Normalize status to single letter
                result[parts[1]] = (status[0] if status else "M", None)
        return result

    # Workspace File Operations

    def get_workspace_files(
        self,
        workspace_id: WorkspaceID,
        transaction: DataModelTransaction,
    ) -> list[str]:
        """List all tracked and untracked file paths in the workspace."""
        workspace = transaction.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        working_dir = self._get_workspace_working_dir(workspace, transaction)

        try:
            returncode, stdout, stderr = run_git_command_local(
                self.concurrency_group,
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=working_dir,
                timeout=_GIT_COMMAND_TIMEOUT,
                is_retry_safe=True,
                check_output=False,
            )
        except GitCommandFailure as e:
            # `git_retry` already retried any transient process-level failures;
            # surface what's left as a typed error rather than a silent empty list.
            logger.info("git ls-files failed for workspace {}: {}", workspace_id, e)
            raise WorkspaceFilesUnavailableError(workspace_id, str(e)) from e

        if returncode != 0:
            # Non-zero exit (e.g. index lock contention) is indistinguishable from
            # an empty workspace at the protocol level if we swallow it. Raise a
            # typed error so callers can surface a retryable signal.
            logger.info("git ls-files failed for workspace {}: rc={} stderr={}", workspace_id, returncode, stderr)
            raise WorkspaceFilesUnavailableError(workspace_id, stderr.strip() or f"git ls-files exited {returncode}")

        file_paths = [f for f in stdout.split("\0") if f.strip()]
        file_paths = [f for f in file_paths if not f.startswith(".git/")]
        return sorted(file_paths)

    def read_file_at_ref(
        self,
        workspace_id: WorkspaceID,
        file_path: str,
        git_ref: str,
        transaction: DataModelTransaction,
    ) -> FileAtRefResult:
        """Read a file's content at a specific git ref."""
        workspace = transaction.get_workspace(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        working_dir = self._get_workspace_working_dir(workspace, transaction)

        returncode, stdout, stderr = run_git_command_local(
            self.concurrency_group,
            ["git", "--no-pager", "show", f"{git_ref}:{file_path}"],
            cwd=working_dir,
            check_output=False,
            timeout=_GIT_COMMAND_TIMEOUT,
            is_retry_safe=True,
        )

        if returncode != 0:
            raise FileNotFoundAtRefError(file_path, git_ref, stderr)

        # Detect binary content (null bytes) and base64-encode
        if "\0" in stdout:
            encoded = base64.b64encode(stdout.encode("utf-8", errors="surrogateescape")).decode("ascii")
            return FileAtRefResult(content=encoded, encoding="base64")

        return FileAtRefResult(content=stdout, encoding="utf-8")
