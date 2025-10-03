import threading
from typing import TypeVar

from loguru import logger
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.serialization import SerializedException
from sculptor.database.models import AgentTaskStateV1
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import LocalSyncDisabledMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncSetupStartedMessage
from sculptor.interfaces.agents.v1.agent import UnexpectedErrorRunnerMessage
from sculptor.primitives.ids import RequestID
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.api import WritableGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.local_sync_service.api import LocalSyncService
from sculptor.services.local_sync_service.api import LocalSyncSessionState
from sculptor.services.local_sync_service.api import SyncSessionInfo
from sculptor.services.local_sync_service.data_types import OtherSyncTransitionInProgressError
from sculptor.services.local_sync_service.data_types import SyncCleanupError
from sculptor.services.local_sync_service.data_types import SyncStartupError
from sculptor.services.local_sync_service.local_sync_errors import LocalSyncError
from sculptor.services.local_sync_service.local_sync_errors import MutagenSyncError
from sculptor.services.local_sync_service.local_sync_session import LocalSyncSession
from sculptor.services.local_sync_service.local_sync_session import SyncUpdateMessenger
from sculptor.services.local_sync_service.local_sync_session import emit_local_sync_posthog_event_if_tracked
from sculptor.services.local_sync_service.mutagen_utils import get_all_sculptor_mutagen_sessions_for_projects
from sculptor.services.local_sync_service.mutagen_utils import mutagen_sync_name_for
from sculptor.services.local_sync_service.mutagen_utils import stop_mutagen_daemon
from sculptor.services.local_sync_service.mutagen_utils import terminate_mutagen_session
from sculptor.services.task_service.api import TaskService
from sculptor.utils.timeout import log_runtime
from sculptor.utils.timeout import log_runtime_decorator

ExceptionT = TypeVar("ExceptionT", bound=Exception)


class DefaultLocalSyncService(LocalSyncService):
    """Manages bidirectional sync between local development environment and task containers using Mutagen"""

    git_repo_service: GitRepoService
    task_service: TaskService
    data_model_service: DataModelService

    # FIXME: add handling for multiple sessions_by_project_id
    _is_daemon_expected_to_have_started: bool = PrivateAttr(default=False)
    _session: LocalSyncSession | None = PrivateAttr(default=None)

    # Used to reject concurrent sync state transitions (does _not_ block/enqueue)
    _sync_transition_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    @property
    def _current_sync_task_id(self) -> TaskID | None:
        info = self._session.session_info if self._session else None
        return info.task_id if info else None

    def get_session_state(self) -> LocalSyncSessionState | None:
        return self._session.state if self._session else None

    @property
    def _is_paused(self) -> bool:
        state = self._session.state if self._session else None
        return state.high_level_status.is_paused if state else False

    def start(self) -> None:
        logger.info("Starting local sync service")
        self._cleanup_dangling_mutagen_sessions()

    def stop(self) -> None:
        """Stop the service and clean up any active syncs."""
        # TODO: making exception to top-level transaction ownership here for now
        with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
            self.cleanup_current_sync(transaction=transaction)
        self.ensure_session_is_stopped()
        if self._is_daemon_expected_to_have_started:
            self._cleanup_dangling_mutagen_sessions()
            stop_mutagen_daemon()

    def ensure_session_is_stopped(self) -> None:
        if self._session:
            self._session.stop()
            self._session = None

    # TODO: Have sculptor add a double-tap test when integration testing
    @log_runtime_decorator("LOCAL_SYNC.sync_to_task")
    def sync_to_task(self, task_id: TaskID, transaction: DataModelTransaction, task: Task | None = None) -> None:
        is_acquired = self._sync_transition_lock.acquire(blocking=False)
        if not is_acquired:
            raise OtherSyncTransitionInProgressError(action="sync to task", new_task_id=task_id)
        try:
            # All this gets our params and is mostly type guarding
            if task is None:
                task = self.task_service.get_task(task_id=task_id, transaction=transaction)
            assert task is not None, f"Task {task_id} not found"
            current_state = task.current_state
            assert isinstance(current_state, AgentTaskStateV1)
            branch_name = current_state.branch_name
            assert branch_name is not None, f"Impossible: Branch name is None for task {task_id}"
            project = transaction.get_project(task.project_id)
            assert project is not None, f"Impossible: Project {task.project_id} not found"

            self._sync_to_task(transaction, task, project, branch_name)
        finally:
            self._sync_transition_lock.release()

    def _sync_to_task(self, transaction: DataModelTransaction, task: Task, project: Project, branch_name: str) -> None:
        """Start bidirectional working tree + unidirectional git sync for a task."""
        logger.info("Starting sync for task {}", task.object_id)

        task_env = self.task_service.get_task_environment(task_id=task.object_id, transaction=transaction)
        assert task_env is not None, f"Task environment not found for task {task.object_id}"

        previous_sync = self._session.session_info if self._session else None
        new_info: SyncSessionInfo | None = None
        is_switching_within_same_project = previous_sync is not None and previous_sync.project_id == task.project_id

        try:
            # Disable any currently active sync
            # FIXME: multiple sessions_by_project_id
            if previous_sync:
                try:
                    with log_runtime("LOCAL_SYNC.sync_to_task._unsync_from_previous_task"):
                        self._unsync_from_task(
                            previous_sync.task_id,
                            switching_to_task=is_switching_within_same_project,
                            transaction=transaction,
                        )
                except LocalSyncError as e:
                    logger.error("Failed to cleanly disable previous sync for task {}: {}", previous_sync.task_id, e)

            # sent started message ASAP as we consider everything here setup
            self._send_message(LocalSyncSetupStartedMessage(), task.object_id, transaction)

            self._ensure_no_active_mutagen_sessions_exist_for_project(project_id=task.project_id)

            with self.git_repo_service.open_local_user_git_repo_for_write(
                user_reference=task.user_reference, project=project
            ) as repo:
                if previous_sync and is_switching_within_same_project:
                    new_info = _carry_forward_info(
                        previous_sync,
                        new_task=task,
                        new_sync_branch=branch_name,
                    )
                else:
                    new_info = self._build_new_sync_info(task, repo, target_branch=branch_name)

                self._session = LocalSyncSession.build_and_start(
                    agent_environment=task_env,
                    session_info=new_info,
                    user_repo_path=repo.get_repo_path(),
                    messenger=self._build_update_messenger(new_info),
                )
                self._is_daemon_expected_to_have_started = True
        # An expected known issue such as divergent git state
        except SyncStartupError:
            # we always at least want to send the message
            self._unsync_from_task(
                task_id=task.object_id,
                transaction=transaction,
                is_startup_error=True,
                failed_session_start_info=new_info,
            )
            raise
        # Any other error must be handled generically
        except Exception as e:
            logger.error("Failed to start sync for task {}: {}", task.object_id, e)
            startup_error = _derive_exception(
                SyncStartupError(
                    f"Failed to start sync for task {task.object_id}: {e}",
                    task_id=str(task.object_id),
                    task_branch=branch_name,
                ),
                from_cause=e,
            )
            self._on_exception_send_message(transaction, task.object_id, startup_error)
            self._unsync_from_task(
                task_id=task.object_id,
                transaction=transaction,
                is_startup_error=True,
                failed_session_start_info=new_info,
            )
            raise startup_error from e

        # Setup messages handled by session now
        logger.info("Successfully enabled sync for task {}", task.object_id)

    @log_runtime_decorator("LOCAL_SYNC.unsync_from_task")
    def unsync_from_task(self, task_id: TaskID, transaction: DataModelTransaction) -> None:
        is_acquired = self._sync_transition_lock.acquire(blocking=False)
        if not is_acquired:
            raise OtherSyncTransitionInProgressError(action="unsync from task", new_task_id=task_id)
        try:
            self._unsync_from_task(task_id, transaction)
        finally:
            self._sync_transition_lock.release()

    def _unsync_from_task(
        self,
        task_id: TaskID,
        transaction: DataModelTransaction,
        switching_to_task: bool = False,
        is_startup_error: bool = False,
        failed_session_start_info: SyncSessionInfo | None = None,
    ) -> None:
        """Stop sync and restore original state unless paused.

        NOTE: Should be fairly idempotent because we call this in the event of a startup error as well, to ensure everything is cleaned up.

        Args:
            task_id: The task to disable sync for
            switching_to_task: If True, we're switching to another task (skip restore)
            is_startup_error: If True, this is a startup error and we don't want to save the LocalSyncDisabledMessage.
        """
        if switching_to_task:
            unsync_reason_for_log = "switching to a new task"
        elif is_startup_error:
            unsync_reason_for_log = "startup error cleanup"
        else:
            unsync_reason_for_log = "stopping active sync"
        logger.info("Stopping active sync for task {}: {}", task_id, unsync_reason_for_log)
        unsyncing_info = failed_session_start_info or (self._session.session_info if self._session else None)

        if (not unsyncing_info) or unsyncing_info.task_id != task_id:
            # FIXME: Figure out how we distinguish is_local_syncing_task on the frontend and correct that state at startup if mangled
            # This is a stopgap to enable manual mitigation of the database being out of sync with the current_state due to failed server-termination cleanup
            # Leaving in until persisted local sync has sufficient cleanup/resiliency
            logger.debug("No active sync found for task {}. Sending stop message in case of manual cleanup", task_id)
            self._send_message(LocalSyncDisabledMessage(), task_id, transaction)
            return

        try:
            is_paused = self._is_paused
            self.ensure_session_is_stopped()
            if is_paused:
                logger.info("Unsyncing from paused task {} and leaving behind state as-is", task_id)
                self._send_message(LocalSyncDisabledMessage(), task_id, transaction)
                return

            task = self.task_service.get_task(task_id=task_id, transaction=transaction)
            assert task is not None, f"Task {task_id} not found"
            project = transaction.get_project(task.project_id)
            assert project is not None, f"Project {task.project_id} not found"
            with self.git_repo_service.open_local_user_git_repo_for_write(
                user_reference=task.user_reference, project=project
            ) as repo:
                status = repo.get_current_status()
                if status.is_in_intermediate_state:
                    logger.info(
                        "Unexpected status {}: unsyncing from task {} and leaving behind state as-is",
                        status,
                        task_id,
                    )
                    # NOTE: we shouldn't get here because the session should handle it by pausing,
                    # but in case we race, we air on the side of exiting as the semantics should be the same
                    self._send_message(LocalSyncDisabledMessage(), task_id, transaction)
                    return
                repo.reset_working_directory()

                if not switching_to_task:
                    logger.debug("Restoring original branch: {}", unsyncing_info.original_branch)
                    repo.git_checkout_branch(unsyncing_info.original_branch)

                    # if sync.has_stash:
                    #     assert sync.stash_message is not None, "Stash message is None despite having a stash"
                    #     repo.restore_git_stash(sync.stash_message)
                    # and then restore untracked files if we go back to manual system

        except (GitRepoError, MutagenSyncError) as e:
            # If we managed to stop the session but encountered an error after, still send disabled signal
            if self._session is None:
                self._send_message(LocalSyncDisabledMessage(), task_id, transaction)

            logger.error("Failed to disable sync for task {}: {}", task_id, e)
            cleanup_error = _derive_exception(
                SyncCleanupError(
                    f"Failed to clean up sync for task {task_id}: {e}",
                    task_id=task_id,
                    cleanup_step=self._determine_cleanup_step(e),
                ),
                from_cause=e,
            )
            self._on_exception_send_message(transaction, task_id, cleanup_error)
            raise cleanup_error from e

        if is_startup_error:
            # If this is a startup error, we don't want to save the LocalSyncDisabledMessage
            # because it would be misleading - the sync was never started.
            logger.info("Sync cleanup completed for task {} after startup error", task_id)
            return

        self._send_message(LocalSyncDisabledMessage(), task_id, transaction)

    def cleanup_current_sync(self, transaction: DataModelTransaction) -> None:
        """Clean up current sync (used on shutdown)."""
        current_task_id = self._current_sync_task_id
        if current_task_id is None:
            return
        logger.info("Cleaning up current sync for task {}", current_task_id)
        try:
            self.unsync_from_task(current_task_id, transaction=transaction)
            self.ensure_session_is_stopped()
        except LocalSyncError as e:
            # Log but don't re-raise during shutdown cleanup
            logger.error("Failed to disable sync for task {} during cleanup: {}", current_task_id, e)

    def _build_new_sync_info(self, task: Task, repo: WritableGitRepo, target_branch: str) -> SyncSessionInfo:
        current_state = task.current_state
        assert isinstance(current_state, AgentTaskStateV1)
        original_branch = repo.get_current_git_branch()
        # stash_message = f"sculptor-sync-{task.object_id}"

        return SyncSessionInfo(
            task_id=task.object_id,
            project_id=task.project_id,
            sync_name=mutagen_sync_name_for(task_id=task.object_id, project_id=task.project_id),
            sync_branch=target_branch,
            original_branch=original_branch,
            # has_stash=repo.create_git_stash(stash_message),
            # stash_message=stash_message,
        )

    def _build_update_messenger(self, session_info: SyncSessionInfo) -> SyncUpdateMessenger:
        return SyncUpdateMessenger(
            info=session_info,
            task_service=self.task_service,
            data_model_service=self.data_model_service,
        )

    def _determine_cleanup_step(self, error: Exception) -> str:
        """Determine which cleanup step failed based on the error type."""
        if isinstance(error, MutagenSyncError):
            return "mutagen_termination"
        elif isinstance(error, GitRepoError):
            if hasattr(error, "operation"):
                return f"git_{error.operation}"
            return "git_operation"
        else:
            return "unknown"

    def _ensure_no_active_mutagen_sessions_exist_for_project(self, project_id: ProjectID) -> None:
        existing_sessions = get_all_sculptor_mutagen_sessions_for_projects(lambda: (project_id,))
        try:
            assert len(existing_sessions) == 0, f"{existing_sessions=} but should be empty when starting a new sync"
        except AssertionError as e:
            message = (
                "LOCAL_SYNC_STATE_MISMATCH in project {project_id}:",
                "existing_sessions={existing_sessions} but should be empty when starting a new sync.",
                "Cleaning up existing sessions.",
            )
            log_exception(e, " ".join(message), project_id=project_id, existing_sessions=existing_sessions)
            for session_name in existing_sessions:
                terminate_mutagen_session(session_name)

    def _get_all_project_ids_in_db(self) -> tuple[ProjectID, ...]:
        with self.data_model_service.open_transaction(RequestID(), is_user_request=False) as transaction:
            return tuple(p.object_id for p in transaction.get_projects())

    def _cleanup_dangling_mutagen_sessions(self) -> None:
        """First, finds all sculptor- prefixed mutagen sessions.

        Then if they exist, query for project ids, and terminate the sessions we know are being managed by this db.
        NOTE: we don't have to worry about sending a stop message, because local sync messages are now ephemeral
        """
        existing_sessions = get_all_sculptor_mutagen_sessions_for_projects(self._get_all_project_ids_in_db)
        for session_name in existing_sessions:
            logger.info("Cleaning up dangling mutagen session {}", session_name)
            terminate_mutagen_session(session_name)

    def _send_message(
        self,
        message: LocalSyncSetupStartedMessage | LocalSyncDisabledMessage,  # other messages handled by session
        task_id: TaskID,
        transaction: DataModelTransaction,
    ) -> None:
        self.task_service.create_message(
            message=message,
            task_id=task_id,
            transaction=transaction,
        )
        emit_local_sync_posthog_event_if_tracked(task_id, message)

    def _on_exception_send_message(
        self, transaction: DataModelTransaction, task_id: TaskID, exception: Exception
    ) -> None:
        self.task_service.create_message(
            message=UnexpectedErrorRunnerMessage(error=SerializedException.build(exception), full_output_url=None),
            task_id=task_id,
            transaction=transaction,
        )

    def is_task_synced(self, task_id: TaskID) -> bool:
        return self._current_sync_task_id == task_id


def _carry_forward_info(previous: SyncSessionInfo, new_task: Task, new_sync_branch: str) -> SyncSessionInfo:
    assert previous.project_id == new_task.project_id, "Cannot carry forward stash between different projects"
    return SyncSessionInfo(
        original_branch=previous.original_branch,
        # has_stash=previous.has_stash,
        # stash_message=previous.stash_message,
        project_id=new_task.project_id,
        task_id=new_task.object_id,
        sync_name=mutagen_sync_name_for(new_task.project_id, new_task.object_id),
        sync_branch=new_sync_branch,
    )


def _derive_exception(reraise_and_capture: ExceptionT, from_cause: Exception) -> ExceptionT:
    """Derives a new exception from_cause, carrying forward traceback"""
    try:
        raise reraise_and_capture from from_cause
    except Exception as e:
        assert e is reraise_and_capture, "Derived exception should be the same as the input reraise_and_capture"
    assert reraise_and_capture.__traceback__ is not None, "Derived exception should have a traceback after derivation"
    return reraise_and_capture
