"""App-level service for PR status polling.

Runs a fixed-size worker pool that pulls poll jobs from a priority queue,
executes ``gh`` CLI calls to fetch PR status, caches results, and fans
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
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from queue import Queue
from typing import Literal

from loguru import logger
from pydantic import PrivateAttr

from sculptor.config.user_config import UserConfig
from sculptor.database.models import Workspace
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.service import Service
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.web.cli_status_utils import CliStatusError
from sculptor.web.cli_status_utils import strip_remote_prefix
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.derived import PrStatusInfo
from sculptor.web.pr_status import GithubRateLimit
from sculptor.web.pr_status import build_status_from_open_nodes
from sculptor.web.pr_status import fetch_open_prs_for_token
from sculptor.web.pr_status import fetch_pr_status

# The terminal/non-terminal PR states. Matches ``PrStatusInfo.pr_state``.
_PrState = Literal["none", "open", "merged", "closed"]

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
# Minimum spacing between the *start* of any two API-backed polls, enforced
# globally across the whole worker pool. GitHub's GraphQL guidance is to avoid
# concurrent requests; staggering poll starts keeps the workers from firing
# gh simultaneously and smooths bursts under the per-minute limit. The
# ``gh`` commands we run are GraphQL-backed, so each poll spends real
# GraphQL points — spacing them is what keeps a fleet of workspaces under the
# hourly budget.
_GLOBAL_MIN_POLL_SPACING_SECONDS = 1.5
# How long to suppress all polls for a provider after it returns a rate-limit
# error. The next poll re-checks and re-applies the cooldown if the host is
# still throttling, so this is a probe interval rather than a guess at the
# exact reset time.
_RATE_LIMIT_COOLDOWN_SECONDS = 60.0
# Terminal PR states (merged/closed) never change again, so poll them rarely
# even while the workspace is open.
_TERMINAL_STATE_MULTIPLIER = 10


def _compute_poll_delay(config: UserConfig, *, is_open: bool, pr_state: _PrState) -> float:
    """Compute the next-poll delay for a workspace from the user's settings.

    Closed workspaces get ``pr_poll_interval_seconds * pr_poll_closed_multiplier``.
    Terminal PRs (merged/closed) back off by ``_TERMINAL_STATE_MULTIPLIER``
    regardless of whether the workspace is open, since their status can't
    change. The largest applicable multiplier wins. All factors are read from
    ``UserConfig`` per call so a new delay is picked up on the very next poll
    cycle after a settings change.
    """
    base = max(float(config.pr_poll_interval_seconds), _MIN_POLL_INTERVAL_SECONDS)
    multiplier = 1.0
    if not is_open:
        multiplier = max(multiplier, float(max(1, config.pr_poll_closed_multiplier)))
    if pr_state in ("merged", "closed"):
        multiplier = max(multiplier, float(_TERMINAL_STATE_MULTIPLIER))
    return base * multiplier


def _compute_round_interval(config: UserConfig) -> float:
    """Base interval between batched search rounds (before the governor).

    One batched ``search`` round is cheap regardless of workspace count, so the
    base is just the configured interval (floored at ``_MIN_POLL_INTERVAL_SECONDS``).
    The governor (``_compute_governed_interval``) stretches this under budget
    pressure; the per-workspace fallback keeps its own ``_compute_poll_delay``
    cadence either way.
    """
    return max(float(config.pr_poll_interval_seconds), _MIN_POLL_INTERVAL_SECONDS)


# GitHub's GraphQL rate limit is a rolling one-hour budget that refills at
# ``resetAt``; the governor projects hourly spend over this window.
_RATE_LIMIT_WINDOW_SECONDS = 3600.0
# Multiplicative step the governor takes per round to lengthen (×) or recover (÷)
# the interval, and the cap on how far it may stretch beyond the base.
_GOVERNOR_STEP_FACTOR = 1.5
_GOVERNOR_MAX_INTERVAL_MULTIPLIER = 20.0
# Recover toward base only once projected spend drops below this fraction of the
# ceiling (hysteresis, so the interval doesn't oscillate round-to-round).
_GOVERNOR_RECOVER_FRACTION = 0.5
# When ``remaining`` falls below this fraction of ``limit`` the wall is near —
# stop polling until the window resets rather than nibbling the last of the budget.
_GOVERNOR_DEFER_REMAINING_FRACTION = 0.05
# A single search round costs only a few points; a cost far above this signals a
# field addition that ballooned the fan-out (complements the Task 4.2 guard).
_MAX_PLAUSIBLE_SEARCH_COST = 50


def _seconds_until_reset(reset_at: str | None) -> float:
    """Parse GitHub's ISO-8601 ``resetAt`` into seconds from now (defensively).

    Returns a full window on a missing/unparseable value or backward clock skew,
    and clamps a far-future value to one window — so a bad timestamp degrades to
    the base cadence rather than crashing or deferring forever.
    """
    if not reset_at:
        return _RATE_LIMIT_WINDOW_SECONDS
    try:
        reset_dt = datetime.datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
    except ValueError:
        return _RATE_LIMIT_WINDOW_SECONDS
    delta = (reset_dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if delta <= 0:
        return 0.0
    return min(delta, _RATE_LIMIT_WINDOW_SECONDS)


def _compute_governed_interval(
    base_interval: float,
    current_interval: float,
    rate_limit: "GithubRateLimit | None",
    budget_fraction: float,
    seconds_until_reset: float,
) -> tuple[float, bool]:
    """Return ``(next round interval, is_throttled)`` for the rate-budget governor.

    Proactively lengthens the round interval before the token's hourly GraphQL
    budget is exhausted. The projection is driven off ``remaining`` (the token's
    *global* budget across every query that hour — search **and** the per-workspace
    fallback fetches), not the search query's ``cost`` alone, which would
    under-count the fallback spend. ``limit`` is read from the response so the
    ceiling scales for tokens with a non-default budget (e.g. GitHub App tokens).

    Behavior: defer to ``reset_at`` when ``remaining`` is critically low; back off
    multiplicatively (up to a cap) when projected hourly spend exceeds
    ``budget_fraction × limit``; recover toward ``base_interval`` (never below it)
    once spend drops comfortably under the ceiling.
    """
    if rate_limit is None or rate_limit.limit <= 0:
        return base_interval, False
    limit = float(rate_limit.limit)
    remaining = float(rate_limit.remaining)
    current_interval = max(current_interval, base_interval)

    # Critically low budget — wait out the window instead of hitting the wall.
    if remaining <= _GOVERNOR_DEFER_REMAINING_FRACTION * limit:
        return max(seconds_until_reset, _MIN_POLL_INTERVAL_SECONDS), True

    ceiling = budget_fraction * limit
    elapsed = min(
        max(_RATE_LIMIT_WINDOW_SECONDS - seconds_until_reset, _MIN_POLL_INTERVAL_SECONDS), _RATE_LIMIT_WINDOW_SECONDS
    )
    spent = max(0.0, limit - remaining)
    projected_hourly_spend = spent / elapsed * _RATE_LIMIT_WINDOW_SECONDS

    max_interval = base_interval * _GOVERNOR_MAX_INTERVAL_MULTIPLIER
    if projected_hourly_spend > ceiling:
        next_interval = min(current_interval * _GOVERNOR_STEP_FACTOR, max_interval)
        return max(next_interval, base_interval), True
    if projected_hourly_spend < ceiling * _GOVERNOR_RECOVER_FRACTION:
        next_interval = max(current_interval / _GOVERNOR_STEP_FACTOR, base_interval)
        return next_interval, next_interval > base_interval
    # Comfortable band — hold the current (possibly already-stretched) interval.
    return current_interval, current_interval > base_interval


class _CooldownDeferred:
    """Sentinel result meaning a poll was skipped because its provider is in
    rate-limit cooldown. Carries how long to wait before trying again so the
    worker can re-enqueue without touching the cache or hitting the API."""

    __slots__ = ("retry_after",)

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after


class _HostThrottle:
    """Thread-safe, process-global throttle shared by all poll workers.

    GitHub's GraphQL rate limit is per authenticated user — one budget shared
    across every workspace and repo — so throttling has to be global, not
    per-workspace. Two responsibilities:

    - **Spacing**: ``reserve_slot`` hands out start times at least
      ``min_interval`` apart, so concurrent workers stagger their gh
      calls instead of firing them at once.
    - **Cooldown**: when GitHub returns a rate-limit error, ``enter_cooldown``
      suppresses every poll until the cooldown expires (queried via
      ``cooldown_remaining``).
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed_start = 0.0
        self._cooldown_until = 0.0

    def cooldown_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._cooldown_until - time.monotonic())

    def enter_cooldown(self, seconds: float) -> None:
        with self._lock:
            until = time.monotonic() + seconds
            # Extend an existing cooldown, never shorten it.
            if until > self._cooldown_until:
                self._cooldown_until = until

    def reserve_slot(self) -> float:
        """Reserve the next global spacing slot; return seconds to wait before starting."""
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_allowed_start)
            self._next_allowed_start = start + self._min_interval
            return start - now


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


@dataclass(frozen=True)
class _RoundCandidate:
    """A workspace eligible to be matched against a batched search round.

    Carries everything the fan-out needs without re-reading git: the workspace's
    repo identity (``name_with_owner``, ``None`` if the origin couldn't be parsed
    into owner/repo — such a workspace is always unmatched and falls back) and
    its ``current_branch`` (the index key), plus its ``target_branch`` for the
    per-workspace derivation. Short-circuited workspaces (no branch / on target /
    non-GitHub) never become candidates.
    """

    workspace_id: WorkspaceID
    state: "_WorkspacePollState"
    working_dir: Path
    current_branch: str
    target_branch: str
    host: str
    name_with_owner: str | None


def _build_pr_index(nodes: Sequence[dict]) -> dict[tuple[str, str], list[dict]]:
    """Index a round's open-PR nodes by ``(nameWithOwner, headRefName)``.

    Transient and per-round — for fan-out only, never a cache key. Preserves node
    order within each bucket (search returns most-recently-updated first, which
    ``_first_matching_target`` relies on). One ``(repo, branch)`` can carry
    several PRs (different bases), hence a list per key.
    """
    index: dict[tuple[str, str], list[dict]] = {}
    for node in nodes:
        repo = (node.get("repository") or {}).get("nameWithOwner")
        head = node.get("headRefName")
        if repo is None or head is None:
            continue
        index.setdefault((repo, head), []).append(node)
    return index


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


def _is_github_url(url: str) -> bool:
    return "github" in _extract_hostname(url).lower()


@dataclass(frozen=True)
class _OriginInfo:
    """Parsed identity of a workspace's ``origin`` remote.

    ``host`` keys the per-(host, token) poll round, so a ``github.com`` workspace
    and a GitHub Enterprise workspace get separate rounds (Risk-5).
    ``name_with_owner`` (``owner/name``, ``.git`` stripped) is compared *exactly*
    against a search node's ``repository.nameWithOwner`` to map the node back to
    this workspace. GitHub returns canonical casing there, so a casing mismatch
    would simply drop the workspace to the per-workspace fallback (acceptable
    degradation).
    """

    host: str
    owner: str
    name: str

    @property
    def name_with_owner(self) -> str:
        return f"{self.owner}/{self.name}"


def _parse_origin_owner_repo(url: str) -> tuple[str, str] | None:
    """Parse ``(owner, name)`` from a git ``origin`` URL, ``.git`` stripped.

    Handles the scp-like (``git@host:owner/repo.git``), ``ssh://``, and http(s)
    forms. Pure string parsing — no git call. Returns ``None`` for any URL that
    does not yield exactly an owner and a repo, so a malformed remote degrades
    (the workspace falls to the fallback) instead of crashing the round.
    """
    if ":" in url and not url.startswith(("https://", "http://", "ssh://")):
        # scp-like ``git@host:owner/repo.git`` — the path follows the first ':'.
        path = url.split(":", 1)[1]
    else:
        path = urllib.parse.urlparse(url).path
    parts = path.strip("/").split("/")
    if len(parts) != 2:
        return None
    owner, repo = parts
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    if not owner or not repo:
        return None
    return owner, repo


def _parse_origin(url: str) -> _OriginInfo | None:
    """Parse a git ``origin`` URL into its ``(host, owner, name)`` identity.

    Reuses ``_extract_hostname`` (consistent with ``_is_github_url``) for the
    host and ``_parse_origin_owner_repo`` for the path. Returns ``None`` if
    either the host or the ``owner/repo`` can't be parsed.
    """
    host = _extract_hostname(url)
    if not host:
        return None
    owner_repo = _parse_origin_owner_repo(url)
    if owner_repo is None:
        return None
    owner, name = owner_repo
    return _OriginInfo(host=host, owner=owner, name=name)


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
    """App-level service that polls PR status using a fixed-size worker pool."""

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
    # Process-global throttle/cooldown shared by every worker. The gh
    # commands are GraphQL-backed and the rate limit is per-user, so spacing
    # and cooldown must be coordinated across the whole pool, not per workspace.
    _throttle: _HostThrottle = PrivateAttr(default_factory=lambda: _HostThrottle(_GLOBAL_MIN_POLL_SPACING_SECONDS))
    # Workspaces matched by the most recent batched search round. A matched
    # workspace rides the cheap batch, so its per-workspace fallback stops
    # rescheduling (checked in _poll_and_handle_result). add/discard are atomic
    # under the GIL; the fallback worker only does a membership test.
    _matched_workspaces: set[WorkspaceID] = PrivateAttr(default_factory=set)
    # Latest ``rateLimit`` snapshot from each host's search round, read by the
    # rate-budget governor. Keyed by host so a github.com round and a GHE round
    # keep separate budgets.
    _rate_limit_by_host: dict[str, GithubRateLimit | None] = PrivateAttr(default_factory=dict)
    # The governor's current (possibly stretched) round interval. None until the
    # first round produces a rateLimit; multiplicative back-off accumulates here.
    _governed_interval: float | None = PrivateAttr(default=None)
    # Hosts whose search round is currently failing (transient), for once-only
    # logging until the round recovers.
    _round_failed_hosts: set[str] = PrivateAttr(default_factory=set)
    # Hosts whose cold-start unmatched-fetch count has already been logged (rule 6).
    _cold_start_logged_hosts: set[str] = PrivateAttr(default_factory=set)

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

    # -- Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        logger.debug("Starting PR polling service")
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            workspaces = transaction.get_workspaces()

        active_workspaces = [w for w in workspaces if not w.is_deleted]
        for workspace in active_workspaces:
            self._add_workspace_poll_state(workspace)

        # Seed an immediate per-workspace fetch for each workspace (open first —
        # the user is looking at them) for instant first status. The batched
        # round (started below) takes over any workspace it matches; this seed
        # is the bounded, one-time cold-start coverage for the rest.
        open_workspaces = [w for w in active_workspaces if w.is_open]
        closed_workspaces = [w for w in active_workspaces if not w.is_open]
        delay = 0.0
        for workspace in open_workspaces:
            self._enqueue(workspace.object_id, delay=delay)
            delay += 0.2
        for workspace in closed_workspaces:
            self._enqueue(workspace.object_id, delay=delay)
            delay += 0.5

        # Fallback worker pool: drains the per-workspace fetch queue (the
        # unmatched-branch fallback + immediate re-polls). Most of the old
        # scheduling machinery survives here, repurposed for the fallback only.
        self._worker_events = [threading.Event() for _ in range(_WORKER_POOL_SIZE)]
        for i in range(_WORKER_POOL_SIZE):
            self.concurrency_group.start_new_thread(
                target=self._worker_loop,
                args=(i,),
                name=f"pr-poll-worker-{i}",
            )
        # Round driver: one thread that, each interval, issues one batched
        # ``search`` query per distinct host and fans the results out per
        # workspace (Change-1). Replaces per-workspace polling for matched PRs.
        self.concurrency_group.start_new_thread(
            target=self._round_loop,
            name="pr-poll-round-driver",
        )
        logger.debug(
            "PR polling service started with {} fallback workers + round driver, {} workspaces",
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
        self._matched_workspaces.discard(workspace_id)

    def on_branch_changed(self, workspace_id: WorkspaceID) -> None:
        """Invalidate cached result and force-enqueue for immediate poll.

        The caller (``_notify_pr_polling_service``) is responsible for
        injecting ``PrStatusInfoCleared`` into the current streaming batch
        so the frontend sees it in the *same* update as the branch change.
        Pushing through the observer queue would delay the signal by one
        loop iteration and silently drop it when the queue is ``None``.
        """
        self._cache.pop(workspace_id, None)
        # The workspace's identity changed — any "matched by the last round" flag
        # is stale, so don't let it suppress this immediate fallback fetch.
        self._matched_workspaces.discard(workspace_id)
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

    # -- Round driver (batched search) -------------------------------------
    #
    # One thread issues a single ``search`` query per distinct host each
    # interval and fans the results out per workspace. A workspace whose open
    # PR matches its target rides this cheap batch (no per-workspace gh call);
    # every other workspace falls back to the per-workspace fetch path on its
    # own cadence (decoupled from the round).

    def _round_loop(self) -> None:
        while not self._shutdown_event.is_set():
            config = get_user_config_instance()
            # Kill switch: skip the batched round too, re-check in ~a minute.
            if not config.pr_polling_enabled:
                self._shutdown_event.wait(_DISABLED_RECHECK_SECONDS)
                continue
            try:
                self._run_round(config)
            except Exception as e:
                # Never let the round thread die — a single bad round must not
                # stop all batched polling.
                log_exception(e, message="PR search round crashed", priority=ExceptionPriority.LOW_PRIORITY)
            self._shutdown_event.wait(self._compute_next_round_interval(config))

    def _compute_next_round_interval(self, config: UserConfig) -> float:
        """Apply the rate-budget governor to pick the next round's interval.

        Reads the most-constrained host's latest ``rateLimit`` and stretches /
        recovers the interval (state in ``_governed_interval``). On a hard defer
        (``remaining`` critically low), also enters the shared rate-limit cooldown
        so the per-workspace fallback backs off too — leaving the cache untouched,
        like ``_CooldownDeferred``, so the user keeps seeing last-known status.
        """
        base_interval = _compute_round_interval(config)
        rate_limit = self._most_constrained_rate_limit()
        if rate_limit is None:
            self._governed_interval = base_interval
            return base_interval

        current_interval = self._governed_interval if self._governed_interval is not None else base_interval
        seconds_until_reset = _seconds_until_reset(rate_limit.reset_at)
        next_interval, is_throttled = _compute_governed_interval(
            base_interval, current_interval, rate_limit, config.pr_poll_budget_fraction, seconds_until_reset
        )
        self._governed_interval = next_interval
        is_deferring = rate_limit.remaining <= _GOVERNOR_DEFER_REMAINING_FRACTION * rate_limit.limit
        if is_throttled:
            logger.debug(
                "PR governor throttling: next round in {:.0f}s (remaining={}/{}, base={:.0f}s)",
                next_interval,
                rate_limit.remaining,
                rate_limit.limit,
                base_interval,
            )
        if is_deferring:
            # Reuse the reactive rate-limit cooldown so fallback fetches pause too
            # until the budget resets (same mechanism a 403 triggers).
            self._throttle.enter_cooldown(max(seconds_until_reset, _MIN_POLL_INTERVAL_SECONDS))
        return next_interval

    def _most_constrained_rate_limit(self) -> GithubRateLimit | None:
        """The latest per-host ``rateLimit`` with the least headroom (lowest remaining fraction)."""
        snapshots = [rl for rl in self._rate_limit_by_host.values() if rl is not None]
        if not snapshots:
            return None
        return min(snapshots, key=lambda rl: (rl.remaining / rl.limit) if rl.limit > 0 else 1.0)

    def _run_round(self, config: UserConfig) -> None:
        """Run one batched search round per distinct host across tracked workspaces."""
        candidates_by_host: dict[str, list[_RoundCandidate]] = {}
        for workspace_id, state in list(self._workspace_poll_state.items()):
            if state.is_deleted:
                continue
            candidate = self._resolve_round_candidate(workspace_id, state)
            if candidate is not None:
                candidates_by_host.setdefault(candidate.host, []).append(candidate)

        for host, candidates in candidates_by_host.items():
            self._run_host_round(host, candidates)

    def _run_host_round(self, host: str, candidates: list[_RoundCandidate]) -> None:
        """Issue one ``search`` query for ``host`` and fan its results out."""
        deferred = self._respect_throttle()
        if deferred is not None:
            # In rate-limit cooldown — skip the batched round; the next round
            # (or the fallback, once the cooldown expires) re-resolves.
            return
        working_dir = candidates[0].working_dir
        try:
            search_result = fetch_open_prs_for_token(working_dir)
        except CliStatusError as e:
            self._handle_round_failure(host, e)
            return

        self._round_failed_hosts.discard(host)
        self._rate_limit_by_host[host] = search_result.rate_limit
        if search_result.rate_limit is not None and search_result.rate_limit.cost > _MAX_PLAUSIBLE_SEARCH_COST:
            # A search round should cost only a few points; a spike means a field
            # addition ballooned the fan-out (lower-bound sanity check for the governor).
            logger.warning(
                "PR search round on {} cost {} points (expected <= {})",
                host,
                search_result.rate_limit.cost,
                _MAX_PLAUSIBLE_SEARCH_COST,
            )
        index = _build_pr_index(search_result.nodes)

        unmatched_count = 0
        for candidate in candidates:
            nodes = (
                index.get((candidate.name_with_owner, candidate.current_branch)) if candidate.name_with_owner else None
            )
            if nodes:
                # The branch carries at least one of the user's open PRs — derive
                # this workspace's status directly from them (open if one targets
                # its base, else a "switch target" mismatch). Either way the round
                # resolves it for free; mark it so its per-workspace fallback
                # stops rescheduling.
                self._matched_workspaces.add(candidate.workspace_id)
                status = build_status_from_open_nodes(candidate.workspace_id, nodes, candidate.target_branch)
                self._emit_status(candidate.workspace_id, status)
            else:
                # No open authored PR on this branch — terminal (merged/closed),
                # no-PR-yet, or a one-round index drop-out. Resolve it via the
                # per-workspace fallback at its own cadence (the search can't tell
                # these apart, so a targeted all-states fetch is required).
                self._matched_workspaces.discard(candidate.workspace_id)
                unmatched_count += 1
                self._enqueue(candidate.workspace_id, delay=0.0)

        if host not in self._cold_start_logged_hosts:
            self._cold_start_logged_hosts.add(host)
            logger.info(
                "PR poll cold start on {}: {} of {} workspace(s) unmatched, fetched via per-workspace fallback",
                host,
                unmatched_count,
                len(candidates),
            )

    def _handle_round_failure(self, host: str, error: CliStatusError) -> None:
        """Route a failed search round: cool down on rate limits, log once on transient."""
        if error.category == "rate_limited":
            self._throttle.enter_cooldown(_RATE_LIMIT_COOLDOWN_SECONDS)
            logger.debug("PR search rate-limited on {}, cooling down {:.0f}s", host, _RATE_LIMIT_COOLDOWN_SECONDS)
            return
        if host not in self._round_failed_hosts:
            self._round_failed_hosts.add(host)
            log_exception(
                error, message=f"PR search round failed on host {host}", priority=ExceptionPriority.LOW_PRIORITY
            )
        else:
            logger.trace("PR search round still failing on {}: {}", host, error)

    def _resolve_round_candidate(
        self, workspace_id: WorkspaceID, state: _WorkspacePollState
    ) -> _RoundCandidate | None:
        """Resolve a workspace for the round, or short-circuit it to ``none``.

        Applies today's short-circuits (rule 4) *before* a workspace can enter a
        round or fallback: not ready (no working_dir) → skip silently; no branch
        info / on the target branch / non-GitHub origin → emit ``none`` with zero
        gh calls. Returns a candidate only for a GitHub workspace off its target
        branch (the population the search can match).
        """
        working_dir = self._resolve_working_dir(workspace_id, state)
        if working_dir is None:
            return None

        current_branch = _get_workspace_current_branch(working_dir)
        target_branch = state.target_branch
        if current_branch is None or target_branch is None:
            self._emit_status(workspace_id, PrStatusInfo(workspace_id=workspace_id, pr_state="none"))
            return None
        if current_branch == strip_remote_prefix(target_branch):
            self._emit_status(workspace_id, PrStatusInfo(workspace_id=workspace_id, pr_state="none"))
            return None

        origin_url = _get_origin_url(working_dir)
        if origin_url is None or not _is_github_url(origin_url):
            self._emit_status(workspace_id, PrStatusInfo(workspace_id=workspace_id, pr_state="none"))
            return None
        if not self._is_gh_available():
            self._emit_status(
                workspace_id,
                PrStatusInfo(
                    workspace_id=workspace_id,
                    pr_state="none",
                    error_category="cli_missing",
                    error_provider="github",
                    error_message="gh CLI not found in PATH",
                ),
            )
            return None

        owner_repo = _parse_origin_owner_repo(origin_url)
        name_with_owner = f"{owner_repo[0]}/{owner_repo[1]}" if owner_repo is not None else None
        return _RoundCandidate(
            workspace_id=workspace_id,
            state=state,
            working_dir=working_dir,
            current_branch=current_branch,
            target_branch=target_branch,
            host=_extract_hostname(origin_url),
            name_with_owner=name_with_owner,
        )

    def _emit_status(self, workspace_id: WorkspaceID, status: PrStatusInfo) -> None:
        """Cache and fan out a status, but only if it changed.

        Holds ``_observer_lock`` across the cache write and the fan-out put() so
        an observer that registers concurrently sees a consistent snapshot.
        """
        with self._observer_lock:
            if status != self._cache.get(workspace_id):
                self._cache[workspace_id] = status
                for observer_queue in self._observers:
                    observer_queue.put(status)

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

        # Provider is in rate-limit cooldown — the poll was skipped without
        # hitting the API. Leave the cached status untouched and retry once
        # the cooldown expires.
        if isinstance(result, _CooldownDeferred):
            self._enqueue(job.workspace_id, delay=max(result.retry_after, _MIN_POLL_INTERVAL_SECONDS))
            return

        # None means workspace wasn't ready (no working_dir yet) — retry soon.
        if result is None:
            self._enqueue(job.workspace_id, delay=_NOT_READY_RETRY_SECONDS)
            return

        # Rule 5 (search-index blip): if we were showing this workspace open and
        # the per-workspace fetch comes back with no PR at all, treat it as a
        # one-round drop-out and keep the cached open status — don't emit a
        # spurious open→none. A real merge/close returns ``merged``/``closed``
        # (never ``none``), so genuine terminal transitions are unaffected; the
        # next round/fallback resolves a true disappearance.
        prev = self._cache.get(job.workspace_id)
        is_open_to_empty_blip = (
            prev is not None
            and prev.pr_state == "open"
            and result.pr_state == "none"
            and result.error_category is None
            and result.mismatched_pr_iid is None
        )
        if is_open_to_empty_blip:
            logger.trace("PR fallback {}: suppressing open→none blip", job.workspace_id)
        else:
            self._emit_status(job.workspace_id, result)

        # A workspace matched by the batched round rides the cheap batch — stop
        # the per-workspace fallback from rescheduling it (rule 3 cost control).
        # If it later drops out of the search, the round re-enqueues a fallback.
        if job.workspace_id in self._matched_workspaces:
            logger.trace("PR fallback {}: matched by search round, not rescheduling fallback", job.workspace_id)
            return

        if result.error_category == "rate_limited":
            # A cooldown was just set — wait it out rather than re-polling at
            # the base interval.
            delay = max(self._throttle.cooldown_remaining(), _MIN_POLL_INTERVAL_SECONDS)
        else:
            delay = _compute_poll_delay(config, is_open=state.is_open, pr_state=result.pr_state)
        self._enqueue(job.workspace_id, delay=delay)

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
            # dict.get never returns None for the dict's own keys
            # pyrefly: ignore [no-matching-overload]
            sleepiest_index = max(self._worker_sleep_until, key=self._worker_sleep_until.get)
            if scheduled_time >= self._worker_sleep_until[sleepiest_index]:
                return
        self._worker_events[sleepiest_index].set()

    def _clear_pending(self, workspace_id: WorkspaceID) -> None:
        with self._pending_lock:
            self._pending.discard(workspace_id)

    def _execute_poll(
        self, workspace_id: WorkspaceID, state: _WorkspacePollState
    ) -> PrStatusInfo | _CooldownDeferred | None:
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

    def _respect_throttle(self) -> _CooldownDeferred | None:
        """Apply the global throttle before an API-backed poll.

        Returns a ``_CooldownDeferred`` if a rate-limit cooldown is currently
        active — the caller should skip the poll (making no API call) and
        re-enqueue. Otherwise reserves a global spacing slot and waits until
        it's due (an interruptible wait so ``stop()`` wakes it immediately),
        then returns None to signal "go ahead".
        """
        remaining = self._throttle.cooldown_remaining()
        if remaining > 0:
            logger.trace("PR poll: in rate-limit cooldown, deferring {:.1f}s", remaining)
            return _CooldownDeferred(remaining)
        wait = self._throttle.reserve_slot()
        if wait > 0:
            self._shutdown_event.wait(timeout=wait)
        return None

    def _note_rate_limit(self, status: PrStatusInfo) -> None:
        """Start a cooldown if the poll was rate-limited."""
        if status.error_category == "rate_limited":
            self._throttle.enter_cooldown(_RATE_LIMIT_COOLDOWN_SECONDS)
            logger.debug("PR poll: rate-limited, cooling down {:.0f}s", _RATE_LIMIT_COOLDOWN_SECONDS)

    def _resolve_working_dir(self, workspace_id: WorkspaceID, state: _WorkspacePollState) -> Path | None:
        """Resolve a workspace's working directory, re-reading from the DB if needed.

        Returns ``None`` if the workspace is gone (marks it deleted) or its
        environment hasn't initialized a working_dir yet. Shared by the batched
        round and the per-workspace fallback fetch.
        """
        working_dir = state.working_dir
        if working_dir is not None:
            return working_dir
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
        return working_dir

    def _fetch_status(
        self, workspace_id: WorkspaceID, state: _WorkspacePollState
    ) -> PrStatusInfo | _CooldownDeferred | None:
        working_dir = self._resolve_working_dir(workspace_id, state)
        if working_dir is None:
            return None

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
            deferred = self._respect_throttle()
            if deferred is not None:
                return deferred
            status = fetch_pr_status(
                workspace_id=workspace_id,
                working_dir=working_dir,
                current_branch=current_branch,
                target_branch=target_branch,
            )
            self._note_rate_limit(status)
            return status

        return PrStatusInfo(workspace_id=workspace_id, pr_state="none")
