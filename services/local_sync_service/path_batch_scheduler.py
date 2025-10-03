import json
import threading
from abc import ABC
from enum import StrEnum
from pathlib import Path
from typing import Collection
from typing import Final
from typing import Iterable
from typing import Sequence
from typing import cast

from loguru import logger
from watchdog.events import DirCreatedEvent
from watchdog.events import DirDeletedEvent
from watchdog.events import DirModifiedEvent
from watchdog.events import DirMovedEvent
from watchdog.events import FileClosedEvent
from watchdog.events import FileClosedNoWriteEvent
from watchdog.events import FileCreatedEvent
from watchdog.events import FileDeletedEvent
from watchdog.events import FileModifiedEvent
from watchdog.events import FileMovedEvent
from watchdog.events import FileOpenedEvent
from watchdog.events import FileSystemEvent
from watchdog.events import FileSystemEventHandler
from watchdog.events import FileSystemMovedEvent

from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import truncate_string
from imbue_core.constants import ExceptionPriority
from imbue_core.itertools import generate_flattened
from imbue_core.pydantic_serialization import MutableModel
from sculptor.interfaces.agents.v1.agent import LocalSyncNonPausingNoticeUnion
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeOfPause
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeUnion
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import BundledThreadingContext
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import DEFAULT_LOCAL_SYNC_DEBOUNCE_SECONDS
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import DEFAULT_LOCAL_SYNC_MAX_DEBOUNCE_SECONDS
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import DebounceController
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import SlightlySaferObserver
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import (
    poll_for_is_lock_acquired_or_give_up_on_stop_event,
)
from sculptor.services.local_sync_service.data_types import NewNoticesInSyncHandlingError
from sculptor.utils.timeout import log_runtime

EVENT_TYPES_TO_IGNORE: Final = (FileOpenedEvent, FileClosedEvent, FileClosedNoWriteEvent)
EVENT_TYPES_TO_WATCH: Final = (
    FileSystemMovedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileCreatedEvent,
    FileMovedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirCreatedEvent,
    DirMovedEvent,
)


# NOTE: Top-level reconciler state combines this and the _ObserverLifecycle enum,
# resulting in the state graph in sculptor/docs/proposals/local_sync_lifecycle.md
class LocalSyncPathBatchSchedulerStatus(StrEnum):
    IDLE = "IDLE"  # Waiting for events
    HANDLING_PENDING = "HANDLING_PENDING"  # Waiting for debounce to complete
    PAUSED_ON_KNOWN_NOTICE = "PAUSED_ON_KNOWN_NOTICE"
    PAUSED_ON_UNEXPECTED_EXCEPTION = "PAUSED_ON_UNEXPECTED_EXCEPTION"
    STOPPING = "STOPPING"  # external event set

    @property
    def is_active(self) -> bool:
        return self in (LocalSyncPathBatchSchedulerStatus.HANDLING_PENDING, LocalSyncPathBatchSchedulerStatus.IDLE)

    @property
    def is_paused(self) -> bool:
        return self in (
            LocalSyncPathBatchSchedulerStatus.PAUSED_ON_KNOWN_NOTICE,
            LocalSyncPathBatchSchedulerStatus.PAUSED_ON_UNEXPECTED_EXCEPTION,
        )


class BatchLifecycleCallbacks(ABC):
    """correspond to the different outcomes that can occur in _fire_callbacks"""

    def on_new_batch_pending(self, triggering_paths_by_tag: dict[str, set[Path]]) -> None:
        """Called when an event moves the scheduler from IDLE to HANDLING_PENDING.

        NOTE: Doesn't currently have any notice or pause info - that is only computed at batch resolution time
        """
        raise NotImplementedError()

    def on_batch_complete(
        self,
        path_batch_by_tag: dict[str, set[Path]],
        nonpause_notices: tuple[LocalSyncNonPausingNoticeUnion, ...],
        prior_status: LocalSyncPathBatchSchedulerStatus,
    ) -> None:
        """Called when a batch of path changes is complete with no PAUSE notices."""
        raise NotImplementedError()

    def on_handling_paused(
        self,
        pending_reconciler_tags: tuple[str, ...],
        nonpause_notices: tuple[LocalSyncNonPausingNoticeUnion, ...],
        pause_notices: tuple[LocalSyncNoticeOfPause, ...],
    ) -> None:
        """Called when handling is paused due to notices (all_notices can include NONBLOCKING notices)."""
        raise NotImplementedError()


def is_path_under_any(query_path: Path, search_paths: Sequence[Path]) -> bool:
    query_path = query_path
    return any(query_path.is_relative_to(ignore_path) for ignore_path in search_paths)


def is_any_path_under(query_paths: Iterable[Path], root_path: Path) -> bool:
    return any(query_path.is_relative_to(root_path) for query_path in query_paths)


def _extract_touched_paths(event: FileSystemEvent) -> set[Path]:
    touched = {Path(str(event.src_path))}
    if hasattr(event, "dest_path") and event.dest_path:
        touched.add(Path(str(event.dest_path)))
    return touched


def _simplify_root_watcher_paths(paths_to_watch: Sequence[Path]) -> tuple[Path, ...]:
    simplified_paths: list[Path] = []
    shortest_to_longest = sorted(paths_to_watch, key=lambda path: len(path.parts))
    for path in shortest_to_longest:
        if is_path_under_any(path, simplified_paths):
            continue
        simplified_paths.append(path)
    return tuple(simplified_paths)


def is_pause_necessary(sync_notices: Iterable[LocalSyncNoticeUnion]) -> bool:
    return any(isinstance(notice, LocalSyncNoticeOfPause) for notice in sync_notices)


def separate_pause_notices(
    sync_notices: Iterable[LocalSyncNoticeUnion],
) -> tuple[tuple[LocalSyncNoticeOfPause, ...], tuple[LocalSyncNonPausingNoticeUnion, ...]]:
    pauses: list[LocalSyncNoticeOfPause] = []
    nonpauses: list[LocalSyncNonPausingNoticeUnion] = []
    for notice in sync_notices:
        if isinstance(notice, LocalSyncNoticeOfPause):
            pauses.append(notice)
        else:
            nonpauses.append(notice)
    return tuple(pauses), tuple(nonpauses)


# Each reconciler filters events from the stream, reports notices, and handles path changes in _fire_callbacks
#
# Subclasses are in git_branch_sync.py and mutagen_filetree_sync.py
class LocalSyncSubReconciler(MutableModel):
    tag: str

    def is_relevant_subpath(self, path: Path) -> bool:
        raise NotImplementedError()

    @property
    def dirs_to_watch(self) -> tuple[Path, ...]:
        raise NotImplementedError()

    @property
    def local_dirs_to_watch(self) -> tuple[Path, ...]:
        raise NotImplementedError()

    @property
    def environment_dirs_to_watch(self) -> tuple[Path, ...]:
        raise NotImplementedError()

    def get_notices(self) -> tuple[LocalSyncNoticeUnion, ...]:
        """notices can be blocking (PAUSE) or non-blocking (NONBLOCKING)"""
        return tuple()

    def handle_path_changes(self, relevant_paths: tuple[Path, ...]) -> None:
        """Handle changes to the paths that are relevant (filtered by LocalSyncPathBatchScheduler)"""
        raise NotImplementedError()


class LocalSyncPathBatchScheduler(FileSystemEventHandler):
    """Batches all source and target paths into a set of touched paths, debounced by debounce_seconds, for no more than max_debounce_seconds.

    Debounce timer is shared between all reconcilers!

    When the callback fires, all registered SubpathReconcilers are called with their respective filtered paths.

    NOTE: The lifecycle management ie pausing etc keeps falling down to this layer,
    so it has accrued a lot of responsibilities.
    """

    def __init__(
        self,
        threading_context: BundledThreadingContext,
        lifecycle_callbacks: BatchLifecycleCallbacks,
        subpath_reconcilers: tuple[LocalSyncSubReconciler, ...],
        debounce_seconds: float = DEFAULT_LOCAL_SYNC_DEBOUNCE_SECONDS,
        max_debounce_seconds: float = DEFAULT_LOCAL_SYNC_MAX_DEBOUNCE_SECONDS,
    ) -> None:
        # Validate that all reconciler tags are unique
        assert len(set(reconciler.tag for reconciler in subpath_reconcilers)) == len(subpath_reconcilers), (
            "tags must be unique"
        )
        self._stop_event = threading_context.stop_event
        self._lifecycle_callbacks = lifecycle_callbacks
        self.debounce = DebounceController(
            threading_context=threading_context,
            debounce_seconds=debounce_seconds,
            max_debounce_seconds=max_debounce_seconds,
            name="fire_reconciler_callbacks",
            callback=self._fire_callbacks,
        )

        self._lock = threading.Lock()

        self._reconciler_by_tag: dict[str, LocalSyncSubReconciler] = {
            reconciler.tag: reconciler for reconciler in subpath_reconcilers
        }
        self._path_batch_by_tag: dict[str, set[Path]] = {reconciler.tag: set() for reconciler in subpath_reconcilers}

        # if we're in a paused state due to an exception, the reconciler will probably spam it repeatedly.
        # this lets us de-escalate the notice to info level after the first time we see it.
        self._last_seen_tagged_exception_type: tuple[str, type] | None = None
        self._last_seen_notices: list[LocalSyncNoticeUnion] = []

    # NOTE: _watchmedo_via_environment.py hacks in it's own path event stream so we don't have to handle it here
    @property
    def top_level_local_dirs_to_register(self) -> tuple[Path, ...]:
        """top-level directories to register for the observer, derived from SubpathReconciler.dirs_to_watch"""
        return _simplify_root_watcher_paths(self.all_required_local_paths)

    @property
    def status(self) -> LocalSyncPathBatchSchedulerStatus:
        if self._last_seen_tagged_exception_type:
            return LocalSyncPathBatchSchedulerStatus.PAUSED_ON_UNEXPECTED_EXCEPTION
        elif is_pause_necessary((*self._last_seen_notices,)):
            return LocalSyncPathBatchSchedulerStatus.PAUSED_ON_KNOWN_NOTICE
        elif self.debounce.is_pending:
            return LocalSyncPathBatchSchedulerStatus.HANDLING_PENDING
        return LocalSyncPathBatchSchedulerStatus.IDLE

    def describe_current_state(self) -> str:
        """Describe the current state of the reconciler, including the number of paths buffered."""
        with poll_for_is_lock_acquired_or_give_up_on_stop_event(self._lock, self._stop_event) as is_lock_acquired:
            if not is_lock_acquired:
                return "LocalSyncPathBatchScheduler: unable to acquire lock to describe current state."
            debounce = self.debounce.describe()
            buffer_json = {tag: sorted(map(str, paths)) for tag, paths in self._path_batch_by_tag.items()}
            buffered_path_count = len({path for paths in self._path_batch_by_tag.values() for path in paths})
            notices = tuple(sorted((notice.describe() for notice in self._last_seen_notices))) or "none"
            ongoing_error = self._last_seen_tagged_exception_type
            status = self.status.value
        state_message = (
            f"LocalSyncPathBatchScheduler ({status=}):",
            f"buffered unique paths: {buffered_path_count}",
            f"buffer state: {json.dumps(buffer_json, indent=4, default=str)}",
            f"notices: {notices}" + (f", last seen tagged exception: {ongoing_error})" if ongoing_error else ""),
            debounce,
        )
        return "\n".join(state_message)

    def on_any_event(self, event: FileSystemEvent) -> None:
        if isinstance(event, EVENT_TYPES_TO_IGNORE):
            return
        self._buffer_relevant_paths(_extract_touched_paths(event))

    # Run in threading.Timer, so we _explode_upwards to capture any exceptions
    def _fire_callbacks(self) -> None:
        """Fire the callback with the touched paths."""
        with poll_for_is_lock_acquired_or_give_up_on_stop_event(self._lock, self._stop_event) as is_lock_acquired:
            if not is_lock_acquired:
                return
            prior_status = self.status
            debug_phase = "known_notice_check"
            try:
                # pause if the reconcilers _know_ they should pause
                _last_seen_notices = self._get_ongoing_known_notices_from_reconcilers()
                self._last_seen_notices = list(_last_seen_notices)
                if is_pause_necessary(self._last_seen_notices):
                    self._handle_pausing()
                    return
                if self._stop_event.is_set():
                    return
                _last_seen_notices = cast(tuple[LocalSyncNonPausingNoticeUnion, ...], _last_seen_notices)

                # once we enter this block we don't want to acknowledge the _stop_event so that file and git syncs happen in unison.
                # otherwise fs and git history will get out of sync.
                for reconciler_tag, path_batch in self._path_batch_by_tag.items():
                    debug_phase = reconciler_tag
                    reconciler = self._reconciler_by_tag[reconciler_tag]
                    if len(path_batch) == 0:
                        continue
                    debounced_by = f"{self.debounce.total_elapsed_seconds:.3f}"
                    logger.trace(
                        "{} handling {} paths (debounced by {}s)", reconciler.tag, len(path_batch), debounced_by
                    )
                    with log_runtime(f"LOCAL_SYNC.{reconciler.tag}.handle_path_changes"):
                        reconciler.handle_path_changes(tuple(path_batch))

                debug_phase = "on_batch_complete"
                self._lifecycle_callbacks.on_batch_complete(self._path_batch_by_tag, _last_seen_notices, prior_status)
                debug_phase = "cleanup"
                self._reset_batch_state()
            except NewNoticesInSyncHandlingError as e:
                notices = generate_flattened((self._last_seen_notices, e.notices))
                self._last_seen_notices = list(sorted(notices, key=lambda notice: notice.priority_for_ordering))
                self._handle_pausing()
                return
            except Exception as e:
                # pause if something unexpected happens
                self._handle_exception_by_pausing(debug_phase, e)
                return

    def _reset_batch_state(self) -> None:
        assert self._lock.locked(), "only for use in locks"
        self.debounce.clear()
        self._last_seen_tagged_exception_type = None
        # slightly order sensitive (would rather not flush if git sync hasn't run)
        self._path_batch_by_tag = {tag: set() for tag in self._reconciler_by_tag.keys()}

    def _get_pending_reconciler_tags(self) -> tuple[str, ...]:
        return tuple(tag for tag, paths in self._path_batch_by_tag.items() if paths)

    def _get_ongoing_known_notices_from_reconcilers(self) -> tuple[LocalSyncNoticeUnion, ...]:
        notices = []
        for tag, reconciler in self._reconciler_by_tag.items():
            with log_runtime(f"LOCAL_SYNC.{tag}.get_notices"):
                notices.extend(reconciler.get_notices())
        return tuple(sorted(notices, key=lambda notice: notice.priority_for_ordering))

    def _handle_exception_by_pausing(self, source_tag: str, exception: Exception) -> None:
        """This is a bit leaky and counter-intuitive but we want to pause even in unknown error states.

        Really we want pause states to be captured by get_notices_without_effecting_state,
        but if the reconciler raises an exception we haven't handled properly,
        we still probably want to pause.
        """
        assert self._lock.locked(), "only for use in locks"
        new_notice = LocalSyncNoticeOfPause(
            source_tag=source_tag,
            reason=truncate_string(f"{source_tag} processing failure: {exception}", 300),
        )
        self._last_seen_notices.append(new_notice)
        self._handle_pausing()
        if self._last_seen_tagged_exception_type != (source_tag, type(exception)):
            self._last_seen_tagged_exception_type = (source_tag, type(exception))
            priority = ExceptionPriority.LOW_PRIORITY
            log_exception(
                exception,
                "local sync paused due to unexpected exception: {reason}",
                priority,
                reason=new_notice.reason,
            )
        else:
            logger.info("local sync paused, unexpected exception continues: {reason}", reason=new_notice.reason)

    def _handle_pausing(self) -> None:
        assert self._lock.locked(), "only for use in locks"
        notices = tuple(sorted((notice.describe() for notice in self._last_seen_notices)))
        if len(notices) == 1:
            logger.info("local sync paused due to notice: {notice}", notice=notices[0])
        else:
            logger.info("local sync paused due to notices:\n * {notices}", notices="\n * ".join(notices))

        pauses, nonpauses = separate_pause_notices(self._last_seen_notices)

        self._lifecycle_callbacks.on_handling_paused(
            pending_reconciler_tags=self._get_pending_reconciler_tags(),
            nonpause_notices=nonpauses,
            pause_notices=pauses,
        )
        self.debounce.restart()

    def _buffer_relevant_paths(self, touched_paths: Collection[Path]) -> None:
        with poll_for_is_lock_acquired_or_give_up_on_stop_event(self._lock, self._stop_event) as is_lock_acquired:
            if not is_lock_acquired:
                return
            updates_by_subpath = {
                tag: {relevant for relevant in touched_paths if reconciler.is_relevant_subpath(relevant)}
                for tag, reconciler in self._reconciler_by_tag.items()
            }

            is_any_path_relevant = any(updates_by_subpath.values())
            if not is_any_path_relevant:
                return

            for reconciler_tag, path_batch in updates_by_subpath.items():
                self._path_batch_by_tag[reconciler_tag].update(path_batch)

            is_new_batch = not self.debounce.is_pending
            self.debounce.start_or_bounce()
            if is_new_batch:
                self._lifecycle_callbacks.on_new_batch_pending(updates_by_subpath)

    def wait_for_final_batch_for_graceful_shutdown(self, timeout: float) -> bool:
        """
        Our scheduler `_buffer_relevant_paths` and batch entrypoint `_fire_callbacks` both start with:
        ... with poll_for_is_lock_acquired_or_give_up_on_stop_event(self._lock, self._stop_event) as is_lock_acquired:
        ...     if not is_lock_acquired: return
        This means if we acquire the lock, here, we can be confident this scheduler will not schedule or handle any new changes.
        """
        # only describing debounce to avoid lock here as something might be horribly wrong / deadlocky
        assert self._stop_event.is_set(), f"parent context should have sent stop event {self.debounce=}"
        is_lock_acquired = self._lock.acquire(blocking=True, timeout=timeout)
        try:
            assert is_lock_acquired, f"failed to acquire lock within {timeout}s: {self.debounce=}"
            self._lock.release()
            return True
        except AssertionError as e:
            message = "wait_for_final_batch_for_graceful_shutdown timeout after {timeout}s"
            log_exception(e, message, ExceptionPriority.HIGH_PRIORITY, timeout=timeout)
            return False

    @property
    def all_required_paths(self) -> tuple[Path, ...]:
        """Get all paths that are required by the reconcilers without any simplification."""
        return tuple(generate_flattened(reconciler.dirs_to_watch for reconciler in self._reconciler_by_tag.values()))

    @property
    def all_required_local_paths(self) -> tuple[Path, ...]:
        """Get all local paths that are required by the reconcilers without any simplification."""
        return tuple(
            generate_flattened(reconciler.local_dirs_to_watch for reconciler in self._reconciler_by_tag.values())
        )

    @property
    def all_required_environment_paths(self) -> tuple[Path, ...]:
        """Get all in-container paths that are required by the reconcilers without any simplification."""
        return tuple(
            generate_flattened(reconciler.environment_dirs_to_watch for reconciler in self._reconciler_by_tag.values())
        )


def register_batch_scheduler_with_observer(
    observer: SlightlySaferObserver, reconciler: LocalSyncPathBatchScheduler
) -> None:
    logger.debug(
        "Registering batched path change reconciler for paths {} (all_required_paths: {})",
        reconciler.top_level_local_dirs_to_register,
        reconciler.all_required_paths,
    )
    for path in reconciler.top_level_local_dirs_to_register:
        observer.schedule(reconciler, str(path), recursive=True, event_filter=list(EVENT_TYPES_TO_WATCH))
