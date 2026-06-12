"""App-level service for PR/MR status polling.

Runs a fixed-size worker pool that pulls poll jobs from a priority queue,
executes CLI calls (gh/glab) to fetch PR status, caches results, and fans
changes out to all registered observer queues. Per-connection scope
filtering is the caller's responsibility — see `project_for_scope` in
`streams.py`, which drops out-of-scope `pr_status_by_workspace_id` entries
from every yielded `StreamingUpdate`.

Replaces the previous thread-per-workspace PrStatusPollingManager.
"""

import datetime
import queue
import shutil
import threading
import time
import urllib.parse
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from queue import Queue

from loguru import logger
from pydantic import PrivateAttr

from imbue_core.async_monkey_patches import log_exception
from imbue_core.concurrency_group import ConcurrencyGroup
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import run_blocking
from imbue_core.sculptor.user_config import UserConfig
from sculptor.database.models import Workspace
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.web.cli_status_utils import strip_remote_prefix
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.derived import PrStatusInfo
from sculptor.web.mr_status import fetch_mr_status
from sculptor.web.pr_status import fetch_pr_status

# Re-enqueue delay when a poll returns None — either the workspace is still
# initializing (no working_dir yet) or _execute_poll caught an exception.
# 3s used to be fine for the "not ready" case but it doubles as a tight
# retry loop on exceptions (including rate-limit responses, since this
# branch has no host-level cooldown). 30s is long enough to not hammer a
# misbehaving host and short enough that a slow-to-initialize workspace
# starts polling promptly once it's ready.
_NOT_READY_RETRY_SECONDS = 30.0
_WORKER_POOL_SIZE = 4
_NOTIFY_THRESHOLD_SECONDS = 10.0
# How long to wait before re-checking config when polling is disabled. Short
# enough that toggling polling back on resumes within ~a minute; long enough
# that the workers aren't spinning while disabled.
_DISABLED_RECHECK_SECONDS = 60.0
# Floor on computed delays. Even if a user sets ``pr_poll_interval_seconds``
# very low and the closed multiplier to 1, we never schedule polls closer
# together than this. Matches the UI's minimum.
_MIN_POLL_INTERVAL_SECONDS = 10.0


def _compute_poll_delay(config: UserConfig, *, is_open: bool) -> float:
    """Compute the next-poll delay for a workspace from the user's settings.

    Closed workspaces get ``pr_poll_interval_seconds * pr_poll_closed_multiplier``.
    Both factors are read from ``UserConfig`` per call so the new delay is
    picked up on the very next poll cycle after a settings change.
    """
    base = max(float(config.pr_poll_interval_seconds), _MIN_POLL_INTERVAL_SECONDS)
    if is_open:
        return base
    multiplier = max(1, config.pr_poll_closed_multiplier)
    return base * multiplier


@dataclass(frozen=True)
class _PollJob:
    """A scheduled poll job for a single workspace.

    ``queue.PriorityQueue`` is a min-heap that pops the smallest item
    first (using ``<``).  ``__lt__`` below sorts by ``scheduled_time``
    only — the earliest-scheduled job is always dequeued first.
    """

    scheduled_time: float
    workspace_id: WorkspaceID = field(compare=False)

    def __lt__(self, other: "_PollJob") -> bool:
        return self.scheduled_time < other.scheduled_time


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _get_workspace_current_branch(working_dir: Path) -> str | None:
    try:
        result = run_blocking(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            timeout=10,
            is_checked=False,
            cwd=working_dir,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def _get_origin_url(repo_path: Path) -> str | None:
    try:
        result = run_blocking(
            ["git", "remote", "get-url", "origin"],
            timeout=10,
            is_checked=False,
            cwd=repo_path,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _extract_hostname(url: str) -> str:
    if ":" in url and not url.startswith(("https://", "http://", "ssh://")):
        return url.split("@", 1)[-1].split(":")[0]
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname or ""


def _is_gitlab_url(url: str) -> bool:
    return "gitlab" in _extract_hostname(url).lower()


def _is_github_url(url: str) -> bool:
    return "github" in _extract_hostname(url).lower()


# ---------------------------------------------------------------------------
# Per-workspace poll state
# ---------------------------------------------------------------------------


class _WorkspacePollState:
    __slots__ = (
        "workspace_id",
        "working_dir",
        "target_branch",
        "is_open",
        "is_deleted",
        "first_failure",
        "poll_generation",
    )

    def __init__(
        self,
        workspace_id: WorkspaceID,
        working_dir: Path | None,
        target_branch: str | None,
        is_open: bool,
    ) -> None:
        self.workspace_id = workspace_id
        self.working_dir = working_dir
        self.target_branch = target_branch
        self.is_open = is_open
        self.is_deleted = False
        self.first_failure: tuple[datetime.datetime, Exception] | None = None
        self.poll_generation: int = 0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PrPollingService(Service):
    """App-level service that polls PR/MR status using a fixed-size worker pool."""

    _data_model_service: DataModelService = PrivateAttr()
    _workspace_service: WorkspaceService = PrivateAttr()
    _job_queue: queue.PriorityQueue = PrivateAttr(default_factory=queue.PriorityQueue)
    _pending: set[WorkspaceID] = PrivateAttr(default_factory=set)
    _pending_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _cache: dict[WorkspaceID, PrStatusInfo] = PrivateAttr(default_factory=dict)
    _workspace_poll_state: dict[WorkspaceID, _WorkspacePollState] = PrivateAttr(default_factory=dict)
    _observers: list[Queue[StreamingUpdateSourceTypes]] = PrivateAttr(default_factory=list)
    # Serializes observer-list mutations and the fan-out so a poll result is
    # never stranded in the cache after the queue it was destined for was
    # orphaned. Held across cache write + fan-out put().
    _observer_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _shutdown_event: threading.Event = PrivateAttr(default_factory=threading.Event)
    # Per-worker wake events and sleep times.  When a worker sleeps waiting
    # for a future job, it registers its scheduled_time in _worker_sleep_until.
    # _enqueue can then find the sleepiest worker and wake only that one.
    _worker_events: list[threading.Event] = PrivateAttr(default_factory=list)
    _worker_sleep_until: dict[int, float] = PrivateAttr(default_factory=dict)
    _worker_sleep_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _gh_available: bool | None = PrivateAttr(default=None)
    _glab_available: bool | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        concurrency_group: ConcurrencyGroup,
        data_model_service: DataModelService,
        workspace_service: WorkspaceService,
    ) -> None:
        super().__init__(concurrency_group=concurrency_group)
        self._data_model_service = data_model_service
        self._workspace_service = workspace_service

    # -- Observer registry (multi-observer fan-out) -----------------------

    def add_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        """Register an observer queue.

        Every cached PR status is immediately pushed to the new observer so
        it sees current state. Per-connection scope filtering is the
        caller's job — `project_for_scope` in `streams.py` drops
        out-of-scope `pr_status_by_workspace_id` entries from every yielded
        `StreamingUpdate`.
        """
        with self._observer_lock:
            self._observers.append(queue)
            for status in self._cache.values():
                queue.put(status)

    def remove_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        """Unregister; safe to call if not registered."""
        with self._observer_lock:
            self._observers = [q for q in self._observers if q is not queue]

    # -- CLI availability (cached per service lifetime) --------------------

    def _is_gh_available(self) -> bool:
        if self._gh_available is True:
            return True
        available = shutil.which("gh") is not None
        if available:
            self._gh_available = True
        return available

    def _is_glab_available(self) -> bool:
        if self._glab_available is True:
            return True
        available = shutil.which("glab") is not None
        if available:
            self._glab_available = True
        return available

    # -- Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        logger.debug("Starting PR polling service")
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            workspaces = transaction.get_workspaces()

        active_workspaces = [w for w in workspaces if not w.is_deleted]
        for workspace in active_workspaces:
            self._add_workspace_poll_state(workspace)

        # Poll open workspaces first (user is looking at them), then closed.
        open_workspaces = [w for w in active_workspaces if w.is_open]
        closed_workspaces = [w for w in active_workspaces if not w.is_open]
        delay = 0.0
        for workspace in open_workspaces:
            self._enqueue(workspace.object_id, delay=delay)
            delay += 0.2
        for workspace in closed_workspaces:
            self._enqueue(workspace.object_id, delay=delay)
            delay += 0.5

        self._worker_events = [threading.Event() for _ in range(_WORKER_POOL_SIZE)]
        for i in range(_WORKER_POOL_SIZE):
            self.concurrency_group.start_new_thread(
                target=self._worker_loop,
                args=(i,),
                name=f"pr-poll-worker-{i}",
            )
        logger.debug(
            "PR polling service started with {} workers, {} workspaces",
            _WORKER_POOL_SIZE,
            len(self._workspace_poll_state),
        )

    def stop(self) -> None:
        logger.debug("Stopping PR polling service")
        self._shutdown_event.set()
        for event in self._worker_events:
            event.set()

    # -- Non-blocking notifications (called by stream_everything) ----------

    def on_workspace_created(self, workspace: Workspace) -> bool:
        """Store poll state for a new or updated workspace.

        For new workspaces, polling is deferred until ``on_workspace_ready``
        is called (when the first ``WorkspaceBranchInfo`` arrives).

        For existing workspaces, this is also called on updates (e.g. when
        ``is_open`` or ``target_branch`` changes).  If the target branch
        changed, invalidates the cache and re-polls immediately.

        Returns True if the target branch changed (caller should inject
        ``PrStatusInfoCleared`` into the streaming batch).
        """
        prev = self._workspace_poll_state.get(workspace.object_id)
        self._add_workspace_poll_state(workspace)

        target_branch_changed = (
            prev is not None and prev.target_branch is not None and prev.target_branch != workspace.target_branch
        )

        if target_branch_changed:
            self.on_branch_changed(workspace.object_id)
            return True

        if prev is not None and not prev.is_open and workspace.is_open:
            with self._pending_lock:
                self._pending.discard(workspace.object_id)
            self._enqueue(workspace.object_id, delay=0)

        return False

    def on_workspace_ready(self, workspace_id: WorkspaceID) -> None:
        """Enqueue a workspace for its first poll.

        Called when the first ``WorkspaceBranchInfo`` arrives for a
        workspace, indicating that the repo is cloned and ready.
        """
        self._enqueue(workspace_id, delay=0)

    def on_workspace_deleted(self, workspace_id: WorkspaceID) -> None:
        """Mark workspace as deleted so workers skip it."""
        state = self._workspace_poll_state.get(workspace_id)
        if state is not None:
            state.is_deleted = True
        self._cache.pop(workspace_id, None)

    def on_branch_changed(self, workspace_id: WorkspaceID) -> None:
        """Invalidate cached result and force-enqueue for immediate poll.

        The caller (``_notify_pr_polling_service``) is responsible for
        injecting ``PrStatusInfoCleared`` into the current streaming batch
        so the frontend sees it in the *same* update as the branch change.
        Pushing through the observer queue would delay the signal by one
        loop iteration and silently drop it when the queue is ``None``.
        """
        self._cache.pop(workspace_id, None)
        state = self._workspace_poll_state.get(workspace_id)
        if state is not None:
            state.first_failure = None
            state.poll_generation += 1

        # Force-enqueue by clearing pending status first, so this bypasses
        # the dedup guard even if the workspace has a pending 30s re-poll.
        with self._pending_lock:
            self._pending.discard(workspace_id)
        self._enqueue(workspace_id, delay=0)

    # -- Internal ----------------------------------------------------------

    def _add_workspace_poll_state(self, workspace: Workspace) -> None:
        working_dir = self._workspace_service.get_workspace_working_directory(workspace)
        self._workspace_poll_state[workspace.object_id] = _WorkspacePollState(
            workspace_id=workspace.object_id,
            working_dir=working_dir,
            target_branch=workspace.target_branch,
            is_open=workspace.is_open,
        )

    def _enqueue(self, workspace_id: WorkspaceID, delay: float) -> None:
        with self._pending_lock:
            if workspace_id in self._pending:
                logger.trace("PR poll: skip enqueue for {} (already pending)", workspace_id)
                return
            self._pending.add(workspace_id)
        job = _PollJob(
            scheduled_time=time.monotonic() + delay,
            workspace_id=workspace_id,
        )
        logger.trace("PR poll: enqueued {} (delay={:.1f}s)", workspace_id, delay)
        # PriorityQueue is a min-heap: it pops the smallest item first,
        # using _PollJob.__lt__ which compares by scheduled_time.
        # Jobs with delay=0 (branch changes) always sort before delay=30 re-polls.
        self._job_queue.put(job)
        self._wake_sleepiest_worker(delay)

    # -- Worker loop -------------------------------------------------------
    #
    # Each worker repeats:  dequeue → wait for scheduled time → poll → handle result.
    #
    # Jobs are scheduled with an absolute ``time.monotonic()`` timestamp.
    # The priority queue dequeues the earliest job first.  If it isn't due
    # yet, the worker registers its sleep time and waits on a per-worker
    # Event.  When _enqueue inserts an urgent job, it wakes the sleepiest
    # worker (the one waiting the longest).  On early wake, the worker
    # puts its job back and re-dequeues so the urgent job gets picked up.
    #
    # A ``poll_generation`` counter on each workspace's poll state detects
    # branch changes that arrive *during* a CLI call.  If the generation
    # changed, the result is stale and gets discarded.

    def _worker_loop(self, worker_index: int) -> None:
        while not self._shutdown_event.is_set():
            job = self._dequeue_job()
            if job is None:
                continue

            state = self._workspace_poll_state.get(job.workspace_id)
            if state is None or state.is_deleted:
                self._clear_pending(job.workspace_id)
                continue

            if not self._wait_until_ready(job, worker_index):
                continue

            self._poll_and_handle_result(job, state)

    def _dequeue_job(self) -> _PollJob | None:
        """Block until a job is available, or return None after 1s."""
        try:
            return self._job_queue.get(timeout=1.0)
        except queue.Empty:
            return None

    def _wait_until_ready(self, job: _PollJob, worker_index: int) -> bool:
        """Wait for a job's scheduled time to arrive.

        Registers this worker's sleep time so ``_wake_sleepiest_worker``
        can find and wake us if a more urgent job arrives.  On early
        wake, puts the current job back and returns False so the worker
        re-dequeues.

        Returns True if the job is ready to execute, False if it was
        re-queued and the worker should loop back to dequeue.
        """
        wait_time = job.scheduled_time - time.monotonic()
        if wait_time <= 0:
            return True

        event = self._worker_events[worker_index]
        event.clear()
        with self._worker_sleep_lock:
            self._worker_sleep_until[worker_index] = job.scheduled_time

        event.wait(timeout=wait_time)

        with self._worker_sleep_lock:
            self._worker_sleep_until.pop(worker_index, None)

        if self._shutdown_event.is_set():
            return False

        # If we woke before the scheduled time (a more urgent job was
        # inserted), put this job back and re-dequeue.
        if time.monotonic() < job.scheduled_time:
            self._job_queue.put(job)
            return False

        return True

    def _poll_and_handle_result(self, job: _PollJob, state: _WorkspacePollState) -> None:
        """Execute a poll and handle the result: cache, push, and re-enqueue."""
        config = get_user_config_instance()

        # Kill switch: when polling is disabled, skip the CLI invocation
        # entirely and re-check in a minute. The cached last-known-good
        # status remains visible to the user. Toggling polling back on
        # via settings resumes within roughly ``_DISABLED_RECHECK_SECONDS``.
        if not config.pr_polling_enabled:
            self._clear_pending(job.workspace_id)
            self._enqueue(job.workspace_id, delay=_DISABLED_RECHECK_SECONDS)
            return

        gen_before = state.poll_generation
        result = self._execute_poll(job.workspace_id, state)

        # Clear pending *after* the poll so that on_branch_changed()
        # during the poll correctly bypasses the dedup guard.
        self._clear_pending(job.workspace_id)

        # Branch changed during the poll — result is stale, and
        # on_branch_changed already enqueued a fresh job.
        if state.poll_generation != gen_before:
            logger.trace("PR poll: discarding stale result for {} (branch changed during poll)", job.workspace_id)
            return

        if state.is_deleted:
            return

        # None means workspace wasn't ready (no working_dir yet) — retry soon.
        if result is None:
            self._enqueue(job.workspace_id, delay=_NOT_READY_RETRY_SECONDS)
            return

        # Push to all observers if the status changed. Hold _observer_lock
        # across the cache write and the fan-out put() so an observer that
        # registers concurrently sees a consistent cache snapshot.
        with self._observer_lock:
            if result != self._cache.get(job.workspace_id):
                self._cache[job.workspace_id] = result
                for queue in self._observers:
                    queue.put(result)

        self._enqueue(job.workspace_id, delay=_compute_poll_delay(config, is_open=state.is_open))

    def _wake_sleepiest_worker(self, delay: float) -> None:
        """Wake the worker sleeping the longest, but only if the new job is more urgent.

        Skips the wake entirely if:
        - delay >= _NOTIFY_THRESHOLD_SECONDS (routine re-polls aren't urgent)
        - no worker is sleeping on a job scheduled later than this one
        """
        if delay >= _NOTIFY_THRESHOLD_SECONDS:
            return
        scheduled_time = time.monotonic() + delay
        with self._worker_sleep_lock:
            if not self._worker_sleep_until:
                return
            sleepiest_index = max(self._worker_sleep_until, key=lambda index: self._worker_sleep_until[index])
            if scheduled_time >= self._worker_sleep_until[sleepiest_index]:
                return
        self._worker_events[sleepiest_index].set()

    def _clear_pending(self, workspace_id: WorkspaceID) -> None:
        with self._pending_lock:
            self._pending.discard(workspace_id)

    def _execute_poll(self, workspace_id: WorkspaceID, state: _WorkspacePollState) -> PrStatusInfo | None:
        try:
            status = self._fetch_status(workspace_id, state)
            state.first_failure = None
            return status
        except Exception as e:
            if state.first_failure is None:
                state.first_failure = (datetime.datetime.now(), e)
                log_exception(
                    e, message="Failed to get PR status for workspace", priority=ExceptionPriority.LOW_PRIORITY
                )
                return None
            original_time, original_exc = state.first_failure
            logger.trace(
                "Still failing to get PR status: {} (original was {} @ {})",
                e,
                type(original_exc),
                original_time.isoformat(),
            )
            return None

    def _fetch_status(self, workspace_id: WorkspaceID, state: _WorkspacePollState) -> PrStatusInfo | None:
        working_dir = state.working_dir

        # Re-read from DB if working_dir not yet available (environment may have initialized)
        if working_dir is None:
            with self._data_model_service.open_transaction(RequestID()) as transaction:
                workspace = transaction.get_workspace(workspace_id)
            if workspace is None or workspace.is_deleted:
                logger.trace("PR poll {}: workspace deleted or missing in DB", workspace_id)
                state.is_deleted = True
                return None
            working_dir = self._workspace_service.get_workspace_working_directory(workspace)
            if working_dir is None:
                logger.trace("PR poll {}: no working_dir yet", workspace_id)
                return None
            state.working_dir = working_dir
            state.target_branch = workspace.target_branch

        current_branch = _get_workspace_current_branch(working_dir)
        target_branch = state.target_branch
        logger.trace(
            "PR poll {}: working_dir={}, current_branch={}, target_branch={}",
            workspace_id,
            working_dir,
            current_branch,
            target_branch,
        )
        if current_branch is None or target_branch is None:
            logger.trace("PR poll {}: no branch info → pr_state=none", workspace_id)
            return PrStatusInfo(workspace_id=workspace_id, pr_state="none")

        stripped_target = strip_remote_prefix(target_branch)
        if current_branch == stripped_target:
            logger.trace("PR poll {}: on target branch ({}) → pr_state=none", workspace_id, current_branch)
            return PrStatusInfo(workspace_id=workspace_id, pr_state="none")

        origin_url = _get_origin_url(working_dir)
        logger.trace("PR poll {}: origin_url={}", workspace_id, origin_url)

        if origin_url is not None and _is_github_url(origin_url):
            if not self._is_gh_available():
                return PrStatusInfo(
                    workspace_id=workspace_id,
                    pr_state="none",
                    error_category="cli_missing",
                    error_provider="github",
                    error_message="gh CLI not found in PATH",
                )
            return fetch_pr_status(
                workspace_id=workspace_id,
                working_dir=working_dir,
                current_branch=current_branch,
                target_branch=target_branch,
            )

        if origin_url is not None and _is_gitlab_url(origin_url):
            if not self._is_glab_available():
                return PrStatusInfo(
                    workspace_id=workspace_id,
                    pr_state="none",
                    error_category="cli_missing",
                    error_provider="gitlab",
                    error_message="glab CLI not found in PATH",
                )
            return fetch_mr_status(
                workspace_id=workspace_id,
                working_dir=working_dir,
                current_branch=current_branch,
                target_branch=target_branch,
            )

        return PrStatusInfo(workspace_id=workspace_id, pr_state="none")
