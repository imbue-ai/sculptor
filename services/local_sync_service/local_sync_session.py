import threading
from abc import ABC
from pathlib import Path
from typing import TypeVar
from typing import assert_never

from loguru import logger

from imbue_core.constants import ExceptionPriority
from imbue_core.itertools import generate_flattened
from imbue_core.processes.local_process import ObservableThread
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.sculptor.telemetry import PosthogEventModel
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import emit_posthog_event
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.thread_utils import log_exception
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import DockerEnvironment
from sculptor.interfaces.agents.v1.agent import LocalSyncDisabledMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncMessageUnion
from sculptor.interfaces.agents.v1.agent import LocalSyncNonPausingNoticeUnion
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeOfPause
from sculptor.interfaces.agents.v1.agent import LocalSyncSetupAndEnabledMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncSetupProgressMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncSetupStartedMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncSetupStep
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdateCompletedMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdateMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdateMessageUnion
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdatePausedMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdatePendingMessage
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.primitives.ids import RequestID
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import SlightlySaferObserver
from sculptor.services.local_sync_service._watchmedo_via_environment import (
    hack_watchmedo_watcher_into_watchdog_event_queue,
)
from sculptor.services.local_sync_service.api import LocalSyncSessionState
from sculptor.services.local_sync_service.api import SyncSessionInfo
from sculptor.services.local_sync_service.data_types import ExpectedStartupBlocker
from sculptor.services.local_sync_service.data_types import ExpectedSyncStartupError
from sculptor.services.local_sync_service.data_types import SyncCleanupError
from sculptor.services.local_sync_service.git_branch_sync import RepoBranchSyncReconciler
from sculptor.services.local_sync_service.mutagen_filetree_sync import LocalSyncGitStateGuardian
from sculptor.services.local_sync_service.mutagen_filetree_sync import MutagenSyncSession
from sculptor.services.local_sync_service.mutagen_filetree_sync import MutagenSyncSessionReconciler
from sculptor.services.local_sync_service.mutagen_filetree_sync import create_bidirectional_user_prioritized_sync
from sculptor.services.local_sync_service.mutagen_filetree_sync import overwrite_local_with_remote_once
from sculptor.services.local_sync_service.path_batch_scheduler import BatchLifecycleCallbacks
from sculptor.services.local_sync_service.path_batch_scheduler import DEFAULT_LOCAL_SYNC_DEBOUNCE_SECONDS
from sculptor.services.local_sync_service.path_batch_scheduler import DEFAULT_LOCAL_SYNC_MAX_DEBOUNCE_SECONDS
from sculptor.services.local_sync_service.path_batch_scheduler import LocalSyncPathBatchScheduler
from sculptor.services.local_sync_service.path_batch_scheduler import LocalSyncPathBatchSchedulerStatus
from sculptor.services.local_sync_service.path_batch_scheduler import register_batch_scheduler_with_observer
from sculptor.services.task_service.api import TaskService
from sculptor.utils.timeout import log_runtime
from sculptor.utils.timeout import log_runtime_decorator

ExceptionT = TypeVar("ExceptionT", bound=Exception)


def _get_posthog_event_type(message: LocalSyncMessageUnion) -> SculptorPosthogEvent | None:
    match message:
        case LocalSyncSetupStartedMessage():
            return SculptorPosthogEvent.LOCAL_SYNC_SETUP_STARTED
        case LocalSyncSetupProgressMessage():
            return None
        case LocalSyncSetupAndEnabledMessage():
            return SculptorPosthogEvent.LOCAL_SYNC_SETUP_AND_ENABLED
        case LocalSyncUpdatePendingMessage():
            return None
        case LocalSyncUpdateCompletedMessage():
            return SculptorPosthogEvent.LOCAL_SYNC_UPDATE_COMPLETED
        case LocalSyncUpdatePausedMessage():
            return SculptorPosthogEvent.LOCAL_SYNC_UPDATE_PAUSED
        case LocalSyncDisabledMessage():
            return SculptorPosthogEvent.LOCAL_SYNC_DISABLED
        case _ as unreachable:
            assert_never(unreachable)


def emit_local_sync_posthog_event_if_tracked(task_id: TaskID, message: LocalSyncMessageUnion) -> None:
    event_type = _get_posthog_event_type(message)
    if event_type is None:
        return
    assert isinstance(message, PosthogEventPayload), (
        f"All messages inherit PosthogEventPayload, but got {type(message)}"
    )
    event = PosthogEventModel(
        name=event_type, component=ProductComponent.LOCAL_SYNC, task_id=str(task_id), payload=message
    )
    emit_posthog_event(event)


def _validate_branches_are_safely_syncable(syncer: "RepoBranchSyncReconciler", task_id: TaskID) -> None:
    """
    Raises an ExpectedSyncStartupError if:
    1. user is ahead of agent branch, because then their changes would get clobbered
    2. branches are divergent
    3. user local checkout is dirty in any way
    Compositing the error messages if multiple are true so user doesn't have to do as many round-trips.
    """
    branch_name = syncer.branch_name

    if syncer.is_user_head_equal_to_agent_head() or syncer.is_agent_a_fastforward_ahead_of_user():
        messages = []
        blockers = []

    elif syncer.is_user_a_fastforward_ahead_of_agent():
        messages = [f"Must push to agent: There are local commits to {branch_name} that would be lost."]
        blockers = [ExpectedStartupBlocker.USER_BRANCH_AHEAD_OF_AGENT]

    else:
        # no one is ahead and we aren't equal, must be diverged
        messages = [f"Must merge into agent: local and agent histories have diverged for {branch_name}."]
        blockers = [ExpectedStartupBlocker.BRANCHES_DIVERGED]

    user_status = syncer.user_repo.repo.get_current_status()
    if not user_status.is_clean_and_safe_to_operate_on:
        message_lines = [
            "Local git state must be pristine with no in-progress operations or untracked files.",
            "Current status:",
            user_status.describe(),
        ]
        messages.append("\n".join(message_lines))
        blockers.append(ExpectedStartupBlocker.USER_GIT_STATE_DIRTY)

    if len(blockers) == 0:
        return

    message = "Cannot start Pairing Mode: " + "Also: ".join(messages)
    raise ExpectedSyncStartupError(message, blockers, task_branch=branch_name)


def _sync_agent_to_user_and_checkout_branch(syncer: RepoBranchSyncReconciler, session_info: SyncSessionInfo):
    # initial git head sync from agent to user
    syncer.user_repo.fetch_and_reset_mixed_on_branch(from_remote=syncer.agent_repo.url)
    if not session_info.is_switching_branches:
        return
    syncer.user_repo.repo.git_checkout_branch(syncer.branch_name)


# NOTE: Combines LocalSyncPathBatchSchedulerStatus and _ObserverLifecycle enums,
# resulting in the state graph in sculptor/docs/proposals/local_sync_lifecycle.md
# separate for testing
class _BatchLifecycleToSendMessageAdapter(BatchLifecycleCallbacks, ABC):
    def send_update_message(self, message: LocalSyncUpdateMessage) -> None:
        raise NotImplementedError()

    def on_new_batch_pending(self, path_batch_by_tag: dict[str, set[Path]]) -> None:
        changed_path_count = len({*generate_flattened(path_batch_by_tag.values())})
        description = f"New batch pending ({changed_path_count=})"
        self.send_update_message(LocalSyncUpdatePendingMessage(event_description=description))

    def on_batch_complete(
        self,
        path_batch_by_tag: dict[str, set[Path]],
        nonpause_notices: tuple[LocalSyncNonPausingNoticeUnion, ...],
        prior_status: LocalSyncPathBatchSchedulerStatus,
    ) -> None:
        changed_path_count = len({*generate_flattened(path_batch_by_tag.values())})

        if prior_status == LocalSyncPathBatchSchedulerStatus.PAUSED_ON_KNOWN_NOTICE:
            description = f"Resuming after resolving known notices ({changed_path_count=})"
            logger.info(description)
            continue_message = LocalSyncUpdateCompletedMessage(
                event_description=description, nonpause_notices=tuple(nonpause_notices), is_resumption=True
            )

        elif prior_status == LocalSyncPathBatchSchedulerStatus.PAUSED_ON_UNEXPECTED_EXCEPTION:
            description = f"Resuming after resolving unexpected exceptions ({changed_path_count=})"
            logger.info(description)
            continue_message = LocalSyncUpdateCompletedMessage(
                event_description=description, nonpause_notices=tuple(nonpause_notices), is_resumption=True
            )

        else:
            description = f"Sending update local sync message ({changed_path_count=})"
            logger.info(description)
            continue_message = LocalSyncUpdateCompletedMessage(
                event_description=description, nonpause_notices=nonpause_notices
            )
        self.send_update_message(continue_message)

    def on_handling_paused(
        self,
        pending_reconciler_tags: tuple[str, ...],
        nonpause_notices: tuple[LocalSyncNonPausingNoticeUnion, ...],
        pause_notices: tuple[LocalSyncNoticeOfPause, ...],
    ) -> None:
        """Called when handling is paused due to notices (all_notices can include NONBLOCKING notices)."""
        pause_message = LocalSyncUpdatePausedMessage(
            event_description=f"Paused due to notices ({pending_reconciler_tags=})",
            nonpause_notices=nonpause_notices,
            pause_notices=pause_notices,
        )
        self.send_update_message(pause_message)


class SyncUpdateMessenger(MutableModel, _BatchLifecycleToSendMessageAdapter):
    info: SyncSessionInfo
    data_model_service: DataModelService
    task_service: TaskService
    hacked_in_stop_event: threading.Event | None = None

    last_sent_message: LocalSyncMessageUnion | None = None

    def send_message(self, message: LocalSyncMessageUnion) -> None:
        if self.hacked_in_stop_event and self.hacked_in_stop_event.is_set():
            logger.info("Not sending update message, sync session is stopped: {}", message)
            return
        with self.data_model_service.open_transaction(request_id=RequestID()) as transaction:
            self.task_service.create_message(message, task_id=self.info.task_id, transaction=transaction)
        self.last_sent_message = message
        emit_local_sync_posthog_event_if_tracked(self.info.task_id, message)

    def send_update_message(self, message: LocalSyncUpdateMessageUnion) -> None:
        self.send_message(message)

    def on_setup_update(self, next_step: LocalSyncSetupStep) -> None:
        self.send_message(LocalSyncSetupProgressMessage(next_step=next_step))

    def on_setup_complete(self) -> None:
        self.send_message(LocalSyncSetupAndEnabledMessage())


class LocalSyncSession(MutableModel):
    """Container for all event messaging, threads (watchdog), sidecare daemons (mutagen) involved in synchronization.

    DOES NOT handle the handling of git and untracked files at the beginning or end of a sync

    Handles constructing the underlying watchers and registering them with the observer,
    while retaining reference to the underlying reconciler (our scheduler) for extracting and handling pause state notices.

    All Reconcilers do initial verification and first sync on build.

    NOTE:
    * This is getting a bit tangled, and should probably be refactored later esp if we migrate to watchman (as we probably should)
    * sculptor/docs/proposals/local_sync_lifecycle.md refers to NoSync, ActiveSync, PausedSync, which is repesented in HighLevelStatus.
    * implemention-wise, the observer STARTS and STOPs, while the LocalSyncPathBatchScheduler PAUSES.
    """

    session_info: SyncSessionInfo
    messenger: SyncUpdateMessenger  # added for caching last message
    observer: SlightlySaferObserver
    watchmedo_over_ssh_thread: ObservableThread

    # debounces events into batches, reports notices for pausing (and nonblocking, ie mutagen conflicts), and handles automatic restarting.
    scheduler: LocalSyncPathBatchScheduler

    mutagen_session: MutagenSyncSession

    @property
    def state(self) -> LocalSyncSessionState | None:
        return LocalSyncSessionState.build_if_sensible(
            info=self.session_info,
            observer=self.observer,
            last_sent_message=self.messenger.last_sent_message,
            scheduler_status=self.scheduler.status,
        )

    @classmethod
    @log_runtime_decorator("LOCAL_SYNC.LocalSyncSession.build_and_start")
    def build_and_start(
        cls,
        agent_environment: Environment,
        session_info: SyncSessionInfo,
        user_repo_path: Path,
        messenger: SyncUpdateMessenger,
        debounce_seconds: float = DEFAULT_LOCAL_SYNC_DEBOUNCE_SECONDS,
        max_debounce_seconds: float = DEFAULT_LOCAL_SYNC_MAX_DEBOUNCE_SECONDS,
    ) -> "LocalSyncSession":
        messenger.on_setup_update(next_step=LocalSyncSetupStep.VALIDATE_GIT_STATE_SAFETY)
        with log_runtime("LOCAL_SYNC.RepoBranchSyncReconciler.build"):
            git_sync_reconciler = RepoBranchSyncReconciler.build(
                branch_name=session_info.sync_branch,
                user_repo_path=user_repo_path,
                agent_environment=agent_environment,
            )
        with log_runtime("LOCAL_SYNC._validate_branches_are_safely_syncable"):
            _validate_branches_are_safely_syncable(git_sync_reconciler, session_info.task_id)

        messenger.on_setup_update(next_step=LocalSyncSetupStep.MIRROR_AGENT_INTO_LOCAL_REPO)
        with log_runtime("LOCAL_SYNC._sync_agent_to_user_and_checkout_branch"):
            _sync_agent_to_user_and_checkout_branch(git_sync_reconciler, session_info)

        guardian = LocalSyncGitStateGuardian.build(repo_path=user_repo_path, branch_name=session_info.sync_branch)
        # redundant with curernt checks in build_and_establish_safety_and_readiness
        # guardian.validate_state_is_acceptable()
        remote_mutagen_url = agent_environment.get_repo_url_for_mutagen()
        with log_runtime("LOCAL_SYNC.overwrite_local_with_remote_once"):
            overwrite_local_with_remote_once(
                local_path=user_repo_path,
                remote_mutagen_url=remote_mutagen_url,
                session_name=f"{session_info.sync_name}-init",
                snapshot_guard=agent_environment.get_snapshot_guard()
                if isinstance(agent_environment, DockerEnvironment)
                else None,
            )

        messenger.on_setup_update(next_step=LocalSyncSetupStep.BEGIN_TWO_WAY_CONTROLLED_SYNC)

        with log_runtime("LOCAL_SYNC.create_bidirectional_user_prioritized_sync"):
            mutagen_session = create_bidirectional_user_prioritized_sync(
                local_path=user_repo_path,
                remote_mutagen_url=remote_mutagen_url,
                session_name=session_info.sync_name,
                snapshot_guard=agent_environment.get_snapshot_guard()
                if isinstance(agent_environment, DockerEnvironment)
                else None,
            )
        try:
            # NOTE: It seems to me like the spaghetti-ness of this passing the stopped_event around could be made more declarative.
            # Really everything in our context needs to know about it.
            observer = SlightlySaferObserver(name="watchdog_observer")
            messenger.hacked_in_stop_event = observer.stopped_event
            mutagen_reconciler = MutagenSyncSessionReconciler(
                session=mutagen_session,
                guardian=guardian,
                stop_event=observer.stopped_event,
            )

            scheduler = LocalSyncPathBatchScheduler(
                threading_context=observer.threading_context,
                lifecycle_callbacks=messenger,
                subpath_reconcilers=(git_sync_reconciler, mutagen_reconciler),
                debounce_seconds=debounce_seconds,
                max_debounce_seconds=max_debounce_seconds,
            )
            register_batch_scheduler_with_observer(observer, scheduler)
            # needs to be registered after because we're piggie-backing on the event emitter
            watchmedo_over_ssh_thread = hack_watchmedo_watcher_into_watchdog_event_queue(
                observer=observer, agent_environment=agent_environment
            )

            session = cls(
                session_info=session_info,
                messenger=messenger,
                observer=observer,
                scheduler=scheduler,
                mutagen_session=mutagen_session,
                watchmedo_over_ssh_thread=watchmedo_over_ssh_thread,
            )
            observer.start()
            watchmedo_over_ssh_thread.start()
            messenger.on_setup_complete()
        except Exception:
            # TODO: consider sending an error message here and having /enable kick-off enable sequence without blocking for completion
            logger.error("local_sync_session: attempting mutagen cleanup after failed start. {}", session_info)
            mutagen_session.terminate(is_skipped_if_uncreated=True)
            raise
        logger.info(
            "started sync for task {}, branch {} (watchdog observers)", session_info.task_id, session_info.sync_branch
        )
        return session

    def _ensure_observer_cleaned_up(self) -> None:
        logger.trace("Ensuring observer is stopped and joined.")
        self.observer.ensure_stopped(source="session._ensure_observer_cleaned_up")
        self.observer.join(timeout=5)
        try:
            self.watchmedo_over_ssh_thread.join(timeout=5)
        except Exception as e:
            log_exception(e, "Error joining watchmedo_over_ssh_thread", ExceptionPriority.MEDIUM_PRIORITY)

        exited = []
        if not self.observer.is_alive():
            exited.append("observer")
        if not self.watchmedo_over_ssh_thread.is_alive():
            exited.append("watchmedo_over_ssh_thread")
        logger.trace("local sync session joined threads: {}", exited)
        if len(exited) == 2:
            return
        raise SyncCleanupError(
            f"either observer or watchmedo did not stop cleanly {exited=}!",
            task_id=self.session_info.task_id,
            cleanup_step="observer_cleanup",
        )

    def stop(self) -> None:
        # We want this so children (ie mutagent reconciler) will know not to undo any shutdown hard-kills,
        # but we can't always get the watchdog observer to stop cleanly without hard-killing the mutagen session first if necessary.
        # idk why exactly, the watchdog internals are kinda hairball-y.
        #
        # TODO: am bypassing the lifecycle system as seemed to be messing with stuff more
        self.observer.stopped_event.set()

        # This waits for the scheduler lock, ensuring any pending batch has been flushed before we go killing mutagen.
        #
        # We really want mutagen to flush cleanly, but the user could be intentionally trying to kill a bloated/off-the-rails sync session,
        # ie syncing a my_big_data/ dir.
        #
        # So, we have to balance these possibilities for now until we can inspect the mutagen state more precisely
        timeout = 15
        with log_runtime("LOCAL_SYNC.LocalSyncSession.stop.wait_for_final_batch_for_graceful_shutdown"):
            is_fully_flushed = self.scheduler.wait_for_final_batch_for_graceful_shutdown(timeout=timeout)
        if not is_fully_flushed:
            message = (
                "Terminating mutagen in sync teardown after wait_for_final_batch_for_graceful_shutdown timeout of {timeout}s.",
                "This means the final batch of changes may not have fully flushed to the agent,",
                "though it was likely in a bad state or syncing something suspiciously large regardless.",
            )
            # TODO raise to user?
            logger.info(" ".join(message), timeout=timeout)

        self.mutagen_session.terminate()
        self._ensure_observer_cleaned_up()
