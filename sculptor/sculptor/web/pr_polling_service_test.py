import queue
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from sculptor.config.user_config import UserConfig
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.cli_status_utils import CliStatusError
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.derived import PrStatusInfo
from sculptor.web.derived import WorkspaceBranchInfo
from sculptor.web.pr_polling_service import PrPollingService
from sculptor.web.pr_polling_service import _CooldownDeferred
from sculptor.web.pr_polling_service import _DISABLED_RECHECK_SECONDS
from sculptor.web.pr_polling_service import _GLOBAL_MIN_POLL_SPACING_SECONDS
from sculptor.web.pr_polling_service import _HostThrottle
from sculptor.web.pr_polling_service import _MIN_POLL_INTERVAL_SECONDS
from sculptor.web.pr_polling_service import _PollJob
from sculptor.web.pr_polling_service import _RATE_LIMIT_COOLDOWN_SECONDS
from sculptor.web.pr_polling_service import _RoundCandidate
from sculptor.web.pr_polling_service import _TERMINAL_STATE_MULTIPLIER
from sculptor.web.pr_polling_service import _WorkspacePollState
from sculptor.web.pr_polling_service import _build_pr_index
from sculptor.web.pr_polling_service import _compute_poll_delay
from sculptor.web.pr_polling_service import _compute_round_interval
from sculptor.web.pr_polling_service import _parse_origin
from sculptor.web.pr_polling_service import _parse_origin_owner_repo
from sculptor.web.pr_status import GithubRateLimit
from sculptor.web.pr_status import OpenPrSearchResult
from sculptor.web.streams import _notify_pr_polling_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> PrPollingService:
    """Create a PrPollingService without starting workers.

    Uses __new__ to bypass __init__ (which requires real services) and
    sets private attrs directly. Fields that would be typed services are
    set to MagicMock via ``object.__setattr__`` to avoid type checker errors
    about attribute types.
    """
    svc = PrPollingService.__new__(PrPollingService)
    svc._job_queue = queue.PriorityQueue()
    svc._pending = set()
    svc._pending_lock = threading.Lock()
    svc._cache = {}
    svc._workspace_poll_state = {}
    svc._observers = []
    svc._observer_lock = threading.Lock()
    svc._shutdown_event = threading.Event()
    svc._worker_events = [threading.Event() for _ in range(4)]
    svc._worker_sleep_until = {}
    svc._worker_sleep_lock = threading.Lock()
    svc._gh_available = None
    svc._throttle = _HostThrottle(_GLOBAL_MIN_POLL_SPACING_SECONDS)
    svc._matched_workspaces = set()
    svc._rate_limit_by_host = {}
    svc._round_failed_hosts = set()
    svc._cold_start_logged_hosts = set()
    object.__setattr__(svc, "_data_model_service", MagicMock())
    object.__setattr__(svc, "_workspace_service", MagicMock())
    return svc


def _mock_workspace(workspace_id: WorkspaceID | None = None) -> Any:
    workspace = MagicMock()
    workspace.object_id = workspace_id or WorkspaceID()
    workspace.target_branch = "main"
    return workspace


def _add_workspace_poll_state(svc: PrPollingService, workspace_id: WorkspaceID) -> None:
    """Add metadata for a workspace without calling on_workspace_created (avoids mock typing)."""
    svc._workspace_poll_state[workspace_id] = _WorkspacePollState(
        workspace_id=workspace_id,
        working_dir=None,
        target_branch="main",
        is_open=True,
    )


# ---------------------------------------------------------------------------
# CLI availability caching
# ---------------------------------------------------------------------------


def test_gh_available_cached_when_found() -> None:
    svc = _make_service()
    with patch("shutil.which", return_value="/usr/bin/gh"):
        assert svc._is_gh_available() is True
    # Second call should use cached value — shutil.which not called
    with patch("shutil.which", side_effect=AssertionError("should not be called")):
        assert svc._is_gh_available() is True


def test_gh_not_cached_when_missing() -> None:
    svc = _make_service()
    call_count = 0

    def counting_which(name: str) -> None:
        nonlocal call_count
        call_count += 1
        return None

    with patch("shutil.which", side_effect=counting_which):
        assert svc._is_gh_available() is False
        assert svc._is_gh_available() is False
    assert call_count == 2, "shutil.which should be called each time when gh is not found"


def test_gh_becomes_available_after_install() -> None:
    svc = _make_service()
    with patch("shutil.which", return_value=None):
        assert svc._is_gh_available() is False

    # Simulate installing gh
    with patch("shutil.which", return_value="/usr/bin/gh"):
        assert svc._is_gh_available() is True

    # Now should be cached
    with patch("shutil.which", side_effect=AssertionError("should not be called")):
        assert svc._is_gh_available() is True


# ---------------------------------------------------------------------------
# on_workspace_created does NOT enqueue
# ---------------------------------------------------------------------------


def test_on_workspace_created_stores_meta_but_does_not_enqueue() -> None:
    svc = _make_service()
    workspace = _mock_workspace()

    result = svc.on_workspace_created(workspace)

    assert workspace.object_id in svc._workspace_poll_state
    assert svc._job_queue.empty(), "on_workspace_created should not enqueue a job"
    assert len(svc._pending) == 0
    assert result is False


def test_on_workspace_created_target_branch_change_triggers_repoll() -> None:
    svc = _make_service()
    workspace = _mock_workspace()
    workspace.target_branch = "main"

    # Initial creation
    svc.on_workspace_created(workspace)
    assert svc._job_queue.empty()

    # Seed the cache so we can verify it gets cleared
    svc._cache[workspace.object_id] = PrStatusInfo(workspace_id=workspace.object_id, pr_state="open")

    # Simulate target branch change
    workspace.target_branch = "develop"
    result = svc.on_workspace_created(workspace)

    assert result is True
    assert workspace.object_id not in svc._cache, "Cache should be cleared on target branch change"
    assert not svc._job_queue.empty(), "Should enqueue immediate re-poll"
    assert svc._workspace_poll_state[workspace.object_id].poll_generation == 1


def test_on_workspace_created_same_target_branch_does_not_trigger() -> None:
    svc = _make_service()
    workspace = _mock_workspace()
    workspace.target_branch = "main"

    svc.on_workspace_created(workspace)

    # Same target branch — should not trigger
    result = svc.on_workspace_created(workspace)

    assert result is False
    assert svc._job_queue.empty()


# ---------------------------------------------------------------------------
# on_workspace_ready DOES enqueue
# ---------------------------------------------------------------------------


def test_on_workspace_ready_enqueues_job() -> None:
    svc = _make_service()
    workspace_id = WorkspaceID()

    svc.on_workspace_ready(workspace_id)

    assert not svc._job_queue.empty(), "on_workspace_ready should enqueue a job"
    assert workspace_id in svc._pending


# ---------------------------------------------------------------------------
# on_workspace_deleted
# ---------------------------------------------------------------------------


def test_on_workspace_deleted_marks_deleted_and_clears_cache() -> None:
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    svc._cache[workspace_id] = PrStatusInfo(workspace_id=workspace_id, pr_state="open")

    svc.on_workspace_deleted(workspace_id)

    assert svc._workspace_poll_state[workspace_id].is_deleted
    assert workspace_id not in svc._cache


# ---------------------------------------------------------------------------
# on_branch_changed
# ---------------------------------------------------------------------------


def test_on_branch_changed_clears_cache_and_enqueues() -> None:
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    svc._cache[workspace_id] = PrStatusInfo(workspace_id=workspace_id, pr_state="open")

    svc.on_branch_changed(workspace_id)

    assert workspace_id not in svc._cache
    assert not svc._job_queue.empty()
    assert svc._workspace_poll_state[workspace_id].poll_generation == 1


def test_on_branch_changed_bypasses_pending_dedup() -> None:
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)

    # Simulate an already-pending job
    svc._pending.add(workspace_id)

    svc.on_branch_changed(workspace_id)

    # Should still have enqueued (cleared pending then re-added)
    assert not svc._job_queue.empty()


# ---------------------------------------------------------------------------
# _notify_pr_polling_service in streams.py
# ---------------------------------------------------------------------------


def test_notify_first_branch_info_calls_on_workspace_ready() -> None:
    svc = MagicMock(spec=PrPollingService)
    workspace_id = WorkspaceID()
    last_branch: dict[WorkspaceID, str] = {}

    data: list[StreamingUpdateSourceTypes] = [
        WorkspaceBranchInfo(current_branch="feat-1", workspace_id=workspace_id),
    ]
    _notify_pr_polling_service(svc, data, last_branch)

    svc.on_workspace_ready.assert_called_once_with(workspace_id)
    svc.on_branch_changed.assert_not_called()
    assert last_branch[workspace_id] == "feat-1"


def test_notify_same_branch_does_not_trigger_anything() -> None:
    svc = MagicMock(spec=PrPollingService)
    workspace_id = WorkspaceID()
    last_branch: dict[WorkspaceID, str] = {workspace_id: "feat-1"}

    data: list[StreamingUpdateSourceTypes] = [
        WorkspaceBranchInfo(current_branch="feat-1", workspace_id=workspace_id),
    ]
    _notify_pr_polling_service(svc, data, last_branch)

    svc.on_workspace_ready.assert_not_called()
    svc.on_branch_changed.assert_not_called()


def test_notify_branch_change_calls_on_branch_changed() -> None:
    svc = MagicMock(spec=PrPollingService)
    workspace_id = WorkspaceID()
    last_branch: dict[WorkspaceID, str] = {workspace_id: "feat-1"}

    data: list[StreamingUpdateSourceTypes] = [
        WorkspaceBranchInfo(current_branch="feat-2", workspace_id=workspace_id),
    ]
    _notify_pr_polling_service(svc, data, last_branch)

    svc.on_branch_changed.assert_called_once_with(workspace_id)
    svc.on_workspace_ready.assert_not_called()
    assert last_branch[workspace_id] == "feat-2"


def test_notify_none_service_is_noop() -> None:
    workspace_id = WorkspaceID()
    last_branch: dict[WorkspaceID, str] = {}
    data: list[StreamingUpdateSourceTypes] = [
        WorkspaceBranchInfo(current_branch="main", workspace_id=workspace_id),
    ]

    # Should not raise
    _notify_pr_polling_service(None, data, last_branch)


# ---------------------------------------------------------------------------
# Observer queue
# ---------------------------------------------------------------------------


def test_add_observer_pushes_all_cached_results() -> None:
    """A new observer receives every cached PR status. Per-connection scope
    filtering is the caller's job (project_for_scope drops out-of-scope
    pr_status_by_workspace_id entries from every yielded StreamingUpdate).
    """
    svc = _make_service()
    ws1 = WorkspaceID()
    ws2 = WorkspaceID()
    status1 = PrStatusInfo(workspace_id=ws1, pr_state="open")
    status2 = PrStatusInfo(workspace_id=ws2, pr_state="merged")
    svc._cache[ws1] = status1
    svc._cache[ws2] = status2

    q: queue.Queue[StreamingUpdateSourceTypes] = queue.Queue()
    svc.add_observer(q)

    items = []
    while not q.empty():
        items.append(q.get_nowait())
    assert sorted(items, key=lambda s: str(s.workspace_id)) == sorted(
        [status1, status2], key=lambda s: str(s.workspace_id)
    )


def test_remove_observer_stops_delivery() -> None:
    svc = _make_service()
    q: queue.Queue[StreamingUpdateSourceTypes] = queue.Queue()
    svc.add_observer(q)
    svc.remove_observer(q)
    assert svc._observers == []


# ---------------------------------------------------------------------------
# Config-driven poll delay
# ---------------------------------------------------------------------------


def _make_user_config(
    *,
    pr_polling_enabled: bool = True,
    pr_poll_interval_seconds: int = 30,
    pr_poll_closed_multiplier: int = 6,
) -> UserConfig:
    """Build a UserConfig with only the polling-relevant fields set."""
    return UserConfig(
        user_email="test@imbue.com",
        user_id="test_user",
        organization_id="test_org",
        instance_id="test_instance",
        pr_polling_enabled=pr_polling_enabled,
        pr_poll_interval_seconds=pr_poll_interval_seconds,
        pr_poll_closed_multiplier=pr_poll_closed_multiplier,
    )


def test_compute_poll_delay_open_uses_base_interval() -> None:
    config = _make_user_config(pr_poll_interval_seconds=45)
    assert _compute_poll_delay(config, is_open=True, pr_state="open") == 45.0


def test_compute_poll_delay_closed_multiplies_base() -> None:
    config = _make_user_config(pr_poll_interval_seconds=20, pr_poll_closed_multiplier=10)
    assert _compute_poll_delay(config, is_open=False, pr_state="open") == 200.0


def test_compute_poll_delay_floors_base_at_minimum() -> None:
    """Even with a sub-minimum interval, never schedule polls closer than the floor."""
    config = _make_user_config(pr_poll_interval_seconds=1)
    assert _compute_poll_delay(config, is_open=True, pr_state="open") == _MIN_POLL_INTERVAL_SECONDS


def test_compute_poll_delay_multiplier_floors_at_one() -> None:
    """A zero or negative multiplier shouldn't make closed polls more frequent than open."""
    config = _make_user_config(pr_poll_interval_seconds=20, pr_poll_closed_multiplier=0)
    assert _compute_poll_delay(config, is_open=False, pr_state="open") == 20.0


def test_compute_poll_delay_terminal_state_backs_off_when_open() -> None:
    """A merged/closed PR can't change, so an open workspace still polls it rarely."""
    config = _make_user_config(pr_poll_interval_seconds=30)
    expected = 30.0 * _TERMINAL_STATE_MULTIPLIER
    assert _compute_poll_delay(config, is_open=True, pr_state="merged") == expected
    assert _compute_poll_delay(config, is_open=True, pr_state="closed") == expected


def test_compute_poll_delay_terminal_state_takes_largest_multiplier() -> None:
    """Closed workspace + terminal PR uses whichever multiplier is larger."""
    # Closed multiplier (2) would give 60; terminal multiplier wins.
    config = _make_user_config(pr_poll_interval_seconds=30, pr_poll_closed_multiplier=2)
    assert _compute_poll_delay(config, is_open=False, pr_state="merged") == 30.0 * _TERMINAL_STATE_MULTIPLIER
    # A huge closed multiplier beats the terminal multiplier.
    config2 = _make_user_config(pr_poll_interval_seconds=30, pr_poll_closed_multiplier=100)
    assert _compute_poll_delay(config2, is_open=False, pr_state="merged") == 30.0 * 100


# ---------------------------------------------------------------------------
# Kill switch and dynamic re-read
# ---------------------------------------------------------------------------


def test_poll_skips_cli_when_polling_disabled() -> None:
    """When pr_polling_enabled is False, _poll_and_handle_result must not call _execute_poll."""
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    svc._pending.add(workspace_id)

    disabled_config = _make_user_config(pr_polling_enabled=False)

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=disabled_config):
        with patch.object(PrPollingService, "_execute_poll", side_effect=AssertionError("must not be called")):
            job = _PollJob(scheduled_time=0.0, workspace_id=workspace_id)
            svc._poll_and_handle_result(job, svc._workspace_poll_state[workspace_id])

    # Re-enqueued at _DISABLED_RECHECK_SECONDS so the toggle-on path is picked up.
    assert not svc._job_queue.empty()
    rescheduled = svc._job_queue.get_nowait()

    delay = rescheduled.scheduled_time - time.monotonic()
    assert _DISABLED_RECHECK_SECONDS - 1 <= delay <= _DISABLED_RECHECK_SECONDS + 1


def test_poll_proceeds_when_polling_enabled() -> None:
    """The default config has polling enabled; _execute_poll runs and result is cached."""
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    state = svc._workspace_poll_state[workspace_id]
    svc._pending.add(workspace_id)

    enabled_config = _make_user_config(pr_polling_enabled=True)
    success_status = PrStatusInfo(workspace_id=workspace_id, pr_state="open")

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=enabled_config):
        with patch.object(PrPollingService, "_execute_poll", return_value=success_status) as exec_mock:
            job = _PollJob(scheduled_time=0.0, workspace_id=workspace_id)
            svc._poll_and_handle_result(job, state)

    exec_mock.assert_called_once()
    assert svc._cache[workspace_id] == success_status


def test_poll_disabled_preserves_existing_cache() -> None:
    """Disabling polling doesn't wipe the last-known PR status from the cache."""
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    state = svc._workspace_poll_state[workspace_id]
    svc._pending.add(workspace_id)

    last_known = PrStatusInfo(workspace_id=workspace_id, pr_state="open", pr_iid=99)
    svc._cache[workspace_id] = last_known

    disabled_config = _make_user_config(pr_polling_enabled=False)

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=disabled_config):
        with patch.object(PrPollingService, "_execute_poll", side_effect=AssertionError("must not be called")):
            job = _PollJob(scheduled_time=0.0, workspace_id=workspace_id)
            svc._poll_and_handle_result(job, state)

    assert svc._cache[workspace_id] == last_known


def test_poll_uses_configured_open_interval_for_re_enqueue() -> None:
    """After a successful poll on an open workspace, re-enqueue uses config.pr_poll_interval_seconds."""
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    state = svc._workspace_poll_state[workspace_id]
    svc._pending.add(workspace_id)

    config = _make_user_config(pr_poll_interval_seconds=45, pr_poll_closed_multiplier=10)
    success_status = PrStatusInfo(workspace_id=workspace_id, pr_state="open")

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config):
        with patch.object(PrPollingService, "_execute_poll", return_value=success_status):
            job = _PollJob(scheduled_time=0.0, workspace_id=workspace_id)
            svc._poll_and_handle_result(job, state)

    rescheduled = svc._job_queue.get_nowait()

    delay = rescheduled.scheduled_time - time.monotonic()
    # Open workspaces use the base interval (45) regardless of multiplier.
    assert 44 <= delay <= 46


def test_poll_uses_multiplier_for_closed_workspace_re_enqueue() -> None:
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    state = svc._workspace_poll_state[workspace_id]
    state.is_open = False
    svc._pending.add(workspace_id)

    config = _make_user_config(pr_poll_interval_seconds=30, pr_poll_closed_multiplier=10)
    success_status = PrStatusInfo(workspace_id=workspace_id, pr_state="open")

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config):
        with patch.object(PrPollingService, "_execute_poll", return_value=success_status):
            job = _PollJob(scheduled_time=0.0, workspace_id=workspace_id)
            svc._poll_and_handle_result(job, state)

    rescheduled = svc._job_queue.get_nowait()

    delay = rescheduled.scheduled_time - time.monotonic()
    # Closed workspace: 30 * 10 = 300.
    assert 299 <= delay <= 301


def test_poll_dynamic_config_re_read_per_cycle() -> None:
    """Changing the config between cycles takes effect on the very next poll."""
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    state = svc._workspace_poll_state[workspace_id]
    svc._pending.add(workspace_id)

    config_a = _make_user_config(pr_poll_interval_seconds=20)
    config_b = _make_user_config(pr_poll_interval_seconds=120)
    success_status = PrStatusInfo(workspace_id=workspace_id, pr_state="open")

    with patch.object(PrPollingService, "_execute_poll", return_value=success_status):
        # First cycle: config_a
        with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config_a):
            svc._poll_and_handle_result(_PollJob(0.0, workspace_id), state)
        rescheduled = svc._job_queue.get_nowait()
        delay_a = rescheduled.scheduled_time - time.monotonic()
        assert 19 <= delay_a <= 21

        # Mark not-pending so we can drive a second cycle
        svc._pending.add(workspace_id)

        # Second cycle: config_b (much longer interval)
        with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config_b):
            svc._poll_and_handle_result(_PollJob(0.0, workspace_id), state)
        rescheduled = svc._job_queue.get_nowait()
        delay_b = rescheduled.scheduled_time - time.monotonic()
        assert 119 <= delay_b <= 121


# ---------------------------------------------------------------------------
# Global throttle: spacing + cooldown
# ---------------------------------------------------------------------------


def test_host_throttle_reserve_slot_spaces_starts() -> None:
    """Consecutive reservations are spaced at least min_interval apart."""
    throttle = _HostThrottle(min_interval=2.0)
    # First reservation is due immediately.
    assert throttle.reserve_slot() == 0.0
    # The next two are pushed out by min_interval each (no real time elapsed).
    second = throttle.reserve_slot()
    third = throttle.reserve_slot()
    assert 1.9 <= second <= 2.0
    assert 3.9 <= third <= 4.0


def test_host_throttle_cooldown_remaining_tracks_window() -> None:
    throttle = _HostThrottle(min_interval=1.0)
    assert throttle.cooldown_remaining() == 0.0
    throttle.enter_cooldown(30.0)
    assert 29.0 <= throttle.cooldown_remaining() <= 30.0


def test_host_throttle_enter_cooldown_never_shortens() -> None:
    throttle = _HostThrottle(min_interval=1.0)
    throttle.enter_cooldown(60.0)
    # A shorter cooldown must not clobber the longer one already in effect.
    throttle.enter_cooldown(5.0)
    assert throttle.cooldown_remaining() > 50.0


def test_respect_throttle_defers_when_in_cooldown() -> None:
    """When a cooldown is active, no slot is reserved and a deferral is returned."""
    svc = _make_service()
    svc._throttle.enter_cooldown(45.0)

    result = svc._respect_throttle()

    assert isinstance(result, _CooldownDeferred)
    assert 44.0 <= result.retry_after <= 45.0


def test_respect_throttle_allows_when_not_in_cooldown() -> None:
    svc = _make_service()
    # First call is due immediately, so it returns None (proceed) without sleeping.
    assert svc._respect_throttle() is None


def test_note_rate_limit_starts_cooldown_only_for_rate_limited() -> None:
    svc = _make_service()
    workspace_id = WorkspaceID()

    ok = PrStatusInfo(workspace_id=workspace_id, pr_state="open")
    svc._note_rate_limit(ok)
    assert svc._throttle.cooldown_remaining() == 0.0

    limited = PrStatusInfo(
        workspace_id=workspace_id, pr_state="none", error_category="rate_limited", error_provider="github"
    )
    svc._note_rate_limit(limited)
    assert svc._throttle.cooldown_remaining() > 0.0


def test_cooldown_deferred_result_does_not_overwrite_cache() -> None:
    """A deferred poll leaves the last-known status in place and re-enqueues after the cooldown."""
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    state = svc._workspace_poll_state[workspace_id]
    svc._pending.add(workspace_id)

    last_known = PrStatusInfo(workspace_id=workspace_id, pr_state="open", pr_iid=7)
    svc._cache[workspace_id] = last_known

    config = _make_user_config()
    deferred = _CooldownDeferred(retry_after=40.0)

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config):
        with patch.object(PrPollingService, "_execute_poll", return_value=deferred):
            svc._poll_and_handle_result(_PollJob(0.0, workspace_id), state)

    # Cache is untouched, and the workspace is re-enqueued after the cooldown.
    assert svc._cache[workspace_id] == last_known
    rescheduled = svc._job_queue.get_nowait()
    delay = rescheduled.scheduled_time - time.monotonic()
    assert 39 <= delay <= 41


def test_rate_limited_result_re_enqueues_after_cooldown() -> None:
    """A rate-limited result waits out the host cooldown instead of the base interval."""
    svc = _make_service()
    workspace_id = WorkspaceID()
    _add_workspace_poll_state(svc, workspace_id)
    state = svc._workspace_poll_state[workspace_id]
    svc._pending.add(workspace_id)

    # Simulate the cooldown the poll would have set via _note_rate_limit.
    svc._throttle.enter_cooldown(_RATE_LIMIT_COOLDOWN_SECONDS)
    limited = PrStatusInfo(
        workspace_id=workspace_id, pr_state="none", error_category="rate_limited", error_provider="github"
    )
    config = _make_user_config(pr_poll_interval_seconds=30)

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config):
        with patch.object(PrPollingService, "_execute_poll", return_value=limited):
            svc._poll_and_handle_result(_PollJob(0.0, workspace_id), state)

    rescheduled = svc._job_queue.get_nowait()
    delay = rescheduled.scheduled_time - time.monotonic()
    # Re-enqueued at ~the remaining cooldown (60s), not the 30s base interval.
    assert _RATE_LIMIT_COOLDOWN_SECONDS - 2 <= delay <= _RATE_LIMIT_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# origin URL -> (host, owner, name) parsing (Change-1 fan-out, Risk-5 GHE hosts).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, host, owner, name",
    [
        ("https://github.com/imbue-ai/sculptor.git", "github.com", "imbue-ai", "sculptor"),
        ("git@github.com:imbue-ai/sculptor.git", "github.com", "imbue-ai", "sculptor"),
        ("ssh://git@github.com/imbue-ai/sculptor.git", "github.com", "imbue-ai", "sculptor"),
        ("https://github.com/imbue-ai/sculptor", "github.com", "imbue-ai", "sculptor"),
        ("https://github.example.com/org/repo.git", "github.example.com", "org", "repo"),
    ],
)
def test_parse_origin_valid_forms(url: str, host: str, owner: str, name: str) -> None:
    info = _parse_origin(url)
    assert info is not None
    assert info.host == host
    assert info.owner == owner
    assert info.name == name
    # name_with_owner is what the poller compares against repository.nameWithOwner.
    assert info.name_with_owner == f"{owner}/{name}"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/onlyowner",
        "git@github.com:onlyowner.git",
        "https://github.com/",
        "https://github.com/a/b/c",
        "not a url",
        "",
    ],
)
def test_parse_origin_malformed_returns_none(url: str) -> None:
    assert _parse_origin(url) is None


def test_parse_origin_owner_repo_strips_dot_git() -> None:
    # nameWithOwner from GitHub's API never carries .git; origin URLs usually do.
    assert _parse_origin_owner_repo("https://github.com/imbue-ai/sculptor.git") == ("imbue-ai", "sculptor")
    assert _parse_origin_owner_repo("git@github.com:imbue-ai/sculptor.git") == ("imbue-ai", "sculptor")


# ---------------------------------------------------------------------------
# Transient per-round (repo, branch) -> nodes index (Change-1 fan-out).
# ---------------------------------------------------------------------------


def _node(number: int, repo: str = "org/repo", head: str = "feat-1", base: str = "main") -> dict:
    return {
        "number": number,
        "repository": {"nameWithOwner": repo},
        "headRefName": head,
        "baseRefName": base,
    }


def test_build_pr_index_keys_by_repo_and_head_branch() -> None:
    nodes = [_node(1, head="feat-1"), _node(2, repo="org/other", head="feat-2")]
    index = _build_pr_index(nodes)
    assert set(index.keys()) == {("org/repo", "feat-1"), ("org/other", "feat-2")}
    assert [n["number"] for n in index[("org/repo", "feat-1")]] == [1]


def test_build_pr_index_groups_multiple_prs_on_one_branch_preserving_order() -> None:
    # One source branch can carry several PRs (different bases); order is
    # preserved (search returns most-recently-updated first).
    nodes = [_node(10, head="feat-1", base="develop"), _node(11, head="feat-1", base="main")]
    index = _build_pr_index(nodes)
    assert [n["number"] for n in index[("org/repo", "feat-1")]] == [10, 11]


def test_build_pr_index_skips_nodes_missing_repo_or_head() -> None:
    nodes = [{"number": 1, "headRefName": "feat-1"}, {"number": 2, "repository": {"nameWithOwner": "org/repo"}}]
    assert _build_pr_index(nodes) == {}


def test_compute_round_interval_floors_at_minimum() -> None:
    config = _make_user_config(pr_poll_interval_seconds=1)
    assert _compute_round_interval(config) == _MIN_POLL_INTERVAL_SECONDS


def test_compute_round_interval_uses_configured_interval() -> None:
    config = _make_user_config(pr_poll_interval_seconds=45)
    assert _compute_round_interval(config) == 45.0


# ---------------------------------------------------------------------------
# Batched search round: fan-out, Change-2 fallback, short-circuits, cadence.
# ---------------------------------------------------------------------------


_WORKING_DIR = Path("/tmp/repo")


def _open_search_node(
    number: int,
    repo: str = "org/repo",
    head: str = "feat-1",
    base: str = "main",
    mergeable: str | None = None,
    check_state: str | None = None,
    reviews: list[dict] | None = None,
    threads: list[dict] | None = None,
) -> dict:
    """Build one ``... on PullRequest`` search node (open state)."""
    rollup = {"state": check_state} if check_state is not None else None
    node = {
        "number": number,
        "title": f"PR #{number}",
        "url": f"https://github.com/{repo}/pull/{number}",
        "state": "OPEN",
        "baseRefName": base,
        "repository": {"nameWithOwner": repo},
        "headRefName": head,
        "commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]},
        "latestReviews": {"nodes": reviews or []},
        "reviewThreads": {"nodes": threads or []},
    }
    if mergeable is not None:
        node["mergeable"] = mergeable
    return node


def _search_result(nodes: list[dict], rate_limit: GithubRateLimit | None = None) -> OpenPrSearchResult:
    if rate_limit is None:
        rate_limit = GithubRateLimit(cost=3, remaining=4997, limit=5000, reset_at="2026-01-01T00:00:00Z")
    return OpenPrSearchResult(nodes=nodes, rate_limit=rate_limit)


def _candidate(
    svc: PrPollingService,
    workspace_id: WorkspaceID,
    target_branch: str,
    current_branch: str = "feat-1",
    repo: str = "org/repo",
    host: str = "github.com",
    is_open: bool = True,
) -> _RoundCandidate:
    """Register a poll state and build a matching round candidate (no git I/O)."""
    state = _WorkspacePollState(
        workspace_id=workspace_id,
        working_dir=_WORKING_DIR,
        target_branch=target_branch,
        is_open=is_open,
    )
    svc._workspace_poll_state[workspace_id] = state
    return _RoundCandidate(
        workspace_id=workspace_id,
        state=state,
        working_dir=_WORKING_DIR,
        current_branch=current_branch,
        target_branch=target_branch,
        host=host,
        name_with_owner=repo,
    )


def test_round_shared_branch_different_target_keys_by_workspace_id() -> None:
    # Two workspaces on the SAME (repo, head branch) but different targets. One
    # open node (base=main) must yield "open" for the main-targeting workspace
    # and "none + mismatched" for the develop-targeting one — proving the cache
    # is keyed by WorkspaceID, not (repo, branch).
    svc = _make_service()
    ws_main = WorkspaceID()
    ws_dev = WorkspaceID()
    cand_main = _candidate(svc, ws_main, target_branch="main")
    cand_dev = _candidate(svc, ws_dev, target_branch="develop")
    node = _open_search_node(100, base="main")

    with patch.object(PrPollingService, "_respect_throttle", return_value=None):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            return_value=_search_result([node]),
        ):
            svc._run_host_round("github.com", [cand_main, cand_dev])

    assert svc._cache[ws_main].pr_state == "open"
    assert svc._cache[ws_main].pr_iid == 100
    assert svc._cache[ws_dev].pr_state == "none"
    assert svc._cache[ws_dev].mismatched_pr_iid == 100
    assert svc._cache[ws_dev].mismatched_pr_target_branch == "main"
    # Both were resolved by the round, so neither needs a per-workspace fallback.
    assert ws_main in svc._matched_workspaces
    assert ws_dev in svc._matched_workspaces
    assert svc._job_queue.empty()


def test_round_conflicting_node_sets_has_conflicts() -> None:
    # mergeable rides the search node, so a matched open PR's merge-conflict
    # signal survives the round (Goal-4: the CI babysitter's MERGE_CONFLICT).
    svc = _make_service()
    ws = WorkspaceID()
    cand = _candidate(svc, ws, target_branch="main")
    node = _open_search_node(200, base="main", mergeable="CONFLICTING")

    with patch.object(PrPollingService, "_respect_throttle", return_value=None):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            return_value=_search_result([node]),
        ):
            svc._run_host_round("github.com", [cand])

    assert svc._cache[ws].pr_state == "open"
    assert svc._cache[ws].has_conflicts is True


def test_round_unmatched_branch_enqueues_fallback_and_does_not_emit() -> None:
    # A workspace whose branch has no open authored PR in the search is unmatched:
    # the round emits nothing for it and enqueues a per-workspace fallback.
    svc = _make_service()
    ws = WorkspaceID()
    cand = _candidate(svc, ws, target_branch="main", current_branch="feat-no-pr")

    with patch.object(PrPollingService, "_respect_throttle", return_value=None):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            return_value=_search_result([_open_search_node(1, head="other-branch")]),
        ):
            svc._run_host_round("github.com", [cand])

    assert ws not in svc._cache
    assert ws not in svc._matched_workspaces
    assert ws in svc._pending
    assert not svc._job_queue.empty()


def test_round_stashes_rate_limit_for_governor() -> None:
    svc = _make_service()
    cand = _candidate(svc, WorkspaceID(), target_branch="main")
    rate_limit = GithubRateLimit(cost=3, remaining=4000, limit=5000, reset_at="2026-01-01T00:00:00Z")

    with patch.object(PrPollingService, "_respect_throttle", return_value=None):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            return_value=_search_result([], rate_limit=rate_limit),
        ):
            svc._run_host_round("github.com", [cand])

    assert svc._rate_limit_by_host["github.com"] == rate_limit


def test_round_logs_cold_start_unmatched_count_once() -> None:
    svc = _make_service()
    cand = _candidate(svc, WorkspaceID(), target_branch="main", current_branch="feat-no-pr")

    with patch.object(PrPollingService, "_respect_throttle", return_value=None):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            return_value=_search_result([]),
        ):
            with patch("sculptor.web.pr_polling_service.logger") as mock_logger:
                svc._run_host_round("github.com", [cand])
                # Second round on the same host must not re-log the cold start.
                svc._run_host_round("github.com", [cand])

    cold_start_logs = [c for c in mock_logger.info.call_args_list if "cold start" in c.args[0]]
    assert len(cold_start_logs) == 1


def test_round_rate_limited_search_enters_cooldown_and_does_not_emit() -> None:
    svc = _make_service()
    ws = WorkspaceID()
    cand = _candidate(svc, ws, target_branch="main")

    with patch.object(PrPollingService, "_respect_throttle", return_value=None):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            side_effect=CliStatusError("rate_limited", "HTTP 403: API rate limit exceeded"),
        ):
            svc._run_host_round("github.com", [cand])

    assert svc._throttle.cooldown_remaining() > 0
    assert ws not in svc._cache


def test_round_skips_search_when_in_cooldown() -> None:
    # When _respect_throttle reports an active cooldown, the round issues NO
    # search query at all.
    svc = _make_service()
    cand = _candidate(svc, WorkspaceID(), target_branch="main")

    with patch.object(PrPollingService, "_respect_throttle", return_value=_CooldownDeferred(30.0)):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            side_effect=AssertionError("search must not run during cooldown"),
        ):
            svc._run_host_round("github.com", [cand])


def test_round_short_circuit_on_target_issues_no_search() -> None:
    # A workspace on its target branch resolves to `none` with zero gh calls —
    # it never becomes a round candidate, so no search query runs.
    svc = _make_service()
    ws = WorkspaceID()
    _add_workspace_poll_state(svc, ws)
    svc._workspace_poll_state[ws].working_dir = _WORKING_DIR
    svc._workspace_poll_state[ws].target_branch = "origin/main"
    config = _make_user_config()

    with patch("sculptor.web.pr_polling_service._get_workspace_current_branch", return_value="main"):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            side_effect=AssertionError("no search for an on-target workspace"),
        ):
            svc._run_round(config)

    assert svc._cache[ws].pr_state == "none"


def test_round_short_circuit_no_branch_issues_no_search() -> None:
    svc = _make_service()
    ws = WorkspaceID()
    _add_workspace_poll_state(svc, ws)
    svc._workspace_poll_state[ws].working_dir = _WORKING_DIR
    config = _make_user_config()

    with patch("sculptor.web.pr_polling_service._get_workspace_current_branch", return_value=None):
        with patch(
            "sculptor.web.pr_polling_service.fetch_open_prs_for_token",
            side_effect=AssertionError("no search for a branchless workspace"),
        ):
            svc._run_round(config)

    assert svc._cache[ws].pr_state == "none"


def test_fallback_index_blip_open_to_none_is_noop() -> None:
    # Prior cache shows open; the per-workspace fallback returns no PR at all (a
    # one-round search-index drop-out). Rule 5: keep the open status, emit
    # nothing — no spurious open→none transition.
    svc = _make_service()
    ws = WorkspaceID()
    _add_workspace_poll_state(svc, ws)
    state = svc._workspace_poll_state[ws]
    svc._pending.add(ws)
    open_status = PrStatusInfo(workspace_id=ws, pr_state="open", pr_iid=7)
    svc._cache[ws] = open_status

    observer: queue.Queue = queue.Queue()
    svc.add_observer(observer)
    observer.get_nowait()  # drain the replayed open status from add_observer

    empty = PrStatusInfo(workspace_id=ws, pr_state="none")
    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=_make_user_config()):
        with patch.object(PrPollingService, "_execute_poll", return_value=empty):
            svc._poll_and_handle_result(_PollJob(0.0, ws), state)

    assert svc._cache[ws] == open_status
    assert observer.empty()


def test_fallback_terminal_merged_reschedules_at_terminal_cadence() -> None:
    svc = _make_service()
    ws = WorkspaceID()
    _add_workspace_poll_state(svc, ws)
    state = svc._workspace_poll_state[ws]
    svc._pending.add(ws)
    merged = PrStatusInfo(workspace_id=ws, pr_state="merged", pr_iid=9)
    config = _make_user_config(pr_poll_interval_seconds=30)

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config):
        with patch.object(PrPollingService, "_execute_poll", return_value=merged):
            svc._poll_and_handle_result(_PollJob(0.0, ws), state)

    assert svc._cache[ws].pr_state == "merged"
    rescheduled = svc._job_queue.get_nowait()
    delay = rescheduled.scheduled_time - time.monotonic()
    expected = 30.0 * _TERMINAL_STATE_MULTIPLIER
    assert expected - 2 <= delay <= expected


def test_fallback_no_pr_reschedules_at_base_interval_independent_of_round() -> None:
    # A no-PR-yet workspace polls at the base interval via the fallback,
    # decoupled from the round — the round interval doesn't enter the math.
    svc = _make_service()
    ws = WorkspaceID()
    _add_workspace_poll_state(svc, ws)
    state = svc._workspace_poll_state[ws]
    svc._pending.add(ws)
    none_status = PrStatusInfo(workspace_id=ws, pr_state="none")
    config = _make_user_config(pr_poll_interval_seconds=45)

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=config):
        with patch.object(PrPollingService, "_execute_poll", return_value=none_status):
            svc._poll_and_handle_result(_PollJob(0.0, ws), state)

    rescheduled = svc._job_queue.get_nowait()
    delay = rescheduled.scheduled_time - time.monotonic()
    assert 43 <= delay <= 45


def test_fallback_matched_workspace_stops_rescheduling() -> None:
    # Once the round has matched a workspace, a stale fallback fetch emits its
    # result but does NOT reschedule — the round now owns it (rule 3 cost control).
    svc = _make_service()
    ws = WorkspaceID()
    _add_workspace_poll_state(svc, ws)
    state = svc._workspace_poll_state[ws]
    svc._pending.add(ws)
    svc._matched_workspaces.add(ws)
    open_status = PrStatusInfo(workspace_id=ws, pr_state="open", pr_iid=5)

    with patch("sculptor.web.pr_polling_service.get_user_config_instance", return_value=_make_user_config()):
        with patch.object(PrPollingService, "_execute_poll", return_value=open_status):
            svc._poll_and_handle_result(_PollJob(0.0, ws), state)

    assert svc._cache[ws] == open_status
    assert svc._job_queue.empty()
    assert ws not in svc._pending
