"""Unit tests for the perfetto/viztracer tracing module.

The module's import is unconditional, but most of its work only happens once
``start_tracing()`` has been called. These tests cover both the "disabled"
no-op path and the "enabled" path of start → buffer external batches → stop
and merge.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from sculptor.utils import tracing


@pytest.fixture(autouse=True)
def _reset_tracing_state() -> None:
    # Tests in this module mutate module-level state. Reset between cases so
    # tests stay independent and order does not matter.
    tracing._trace_to_path = None
    tracing._tracer = None
    tracing._internal_trace_path = None
    tracing._dropped_event_count = 0
    tracing._invalid_event_count = 0
    tracing._external_events_accepting = False
    with tracing._external_events_lock:
        tracing._external_events.clear()


def test_is_disabled_by_default() -> None:
    assert tracing.is_tracing_enabled() is False
    assert tracing.get_trace_to_path() is None


def test_add_external_events_is_noop_when_disabled() -> None:
    tracing.add_external_events([{"ph": "X", "name": "foo", "ts": 0}], tracing.RENDERER_PID)
    with tracing._external_events_lock:
        assert tracing._external_events == []


def test_start_stop_writes_combined_trace(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    assert tracing.is_tracing_enabled() is True
    assert tracing.get_trace_to_path() == out.resolve()

    # Buffer some renderer events while tracing is active.
    tracing.add_external_events(
        [{"ph": "X", "name": "renderer.boot", "ts": 0, "dur": 1, "cat": "frontend"}],
        tracing.RENDERER_PID,
    )
    tracing.add_external_events(
        [{"ph": "X", "name": "electron.spawn", "ts": 0, "dur": 1, "cat": "electron"}],
        tracing.ELECTRON_MAIN_PID,
    )

    tracing.stop_and_write_trace()

    assert out.exists()
    with open(out) as f:
        data = json.load(f)
    events = data["traceEvents"]
    pids = {event.get("pid") for event in events}
    # All three sources (backend + renderer + electron-main) should be present.
    assert tracing.RENDERER_PID in pids
    assert tracing.ELECTRON_MAIN_PID in pids
    # And the backend pid (its exact value is not fixed) should also be there from viztracer.
    backend_pids = pids - {tracing.RENDERER_PID, tracing.ELECTRON_MAIN_PID, None}
    assert backend_pids, "Expected at least one backend pid from viztracer"

    # Process-name metadata events should label the synthetic sources so they
    # appear with friendly names in Perfetto.
    process_name_events = [e for e in events if e.get("name") == "process_name"]
    name_by_pid = {e["pid"]: e["args"]["name"] for e in process_name_events}
    assert name_by_pid.get(tracing.RENDERER_PID) == "renderer"
    assert name_by_pid.get(tracing.ELECTRON_MAIN_PID) == "electron_main"


def test_start_tracing_is_idempotent(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    assert tracing.start_tracing(out) is True  # armed a fresh session
    first_tracer = tracing._tracer
    assert tracing.start_tracing(out) is False  # already running → no-op, reports it didn't arm
    assert tracing._tracer is first_tracer
    # Tear down so the autouse fixture's reset is clean.
    tracing.stop_and_write_trace()


def test_stop_returns_result_with_counts(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    tracing.add_external_events(
        [
            {"ph": "X", "name": "renderer.a", "ts": 0, "dur": 1},
            {"ph": "X", "name": "renderer.b", "ts": 1, "dur": 1},
        ],
        tracing.RENDERER_PID,
    )
    result = tracing.stop_and_write_trace()
    assert result is not None
    assert result.path == out.resolve()
    assert result.external_event_count == 2
    # viztracer always records at least its own frames, so this is non-zero.
    assert result.backend_event_count > 0


def test_stop_when_disabled_returns_none() -> None:
    assert tracing.stop_and_write_trace() is None


def test_rearm_after_stop_starts_fresh_session(tmp_path: Path) -> None:
    """The whole point of runtime arm/disarm: after a flush the module must be
    ready to arm a brand-new session to a different file. Pins that
    stop_and_write_trace resets state and that a second start builds a fresh
    tracer rather than no-opping (which is what the idempotency guard would do
    if the prior tracer were not cleared)."""
    first = tmp_path / "first.json"
    tracing.start_tracing(first)
    first_tracer = tracing._tracer
    assert tracing.stop_and_write_trace() is not None
    # Disarmed and reset.
    assert tracing.is_tracing_enabled() is False
    assert tracing.get_trace_to_path() is None
    assert tracing._tracer is None

    second = tmp_path / "second.json"
    tracing.start_tracing(second)
    assert tracing.is_tracing_enabled() is True
    assert tracing._tracer is not None
    assert tracing._tracer is not first_tracer
    assert tracing.get_trace_to_path() == second.resolve()
    result = tracing.stop_and_write_trace()
    assert result is not None and result.path == second.resolve()
    assert first.exists() and second.exists()


def test_temp_directory_cleaned_up_after_write(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    internal = tracing._internal_trace_path
    assert internal is not None
    temp_dir = internal.parent
    assert temp_dir.exists()
    tracing.stop_and_write_trace()
    assert not temp_dir.exists(), "viztracer temp dir should be cleaned up on exit"
    # User-facing trace file should still be there.
    assert out.exists()


def test_invalid_events_dropped_with_counter(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    # Pass a deliberately mixed-type batch — the runtime guards in
    # add_external_events are the thing under test, and the static type only
    # describes the happy path. Use ``list[Any]`` so the runtime
    # junk-rejection path gets exercised without a type error.
    batch: list[Any] = [
        {"ph": "X", "name": "good", "ts": 0, "dur": 1},  # valid
        {"name": "missing-ph-and-ts"},  # invalid: missing required keys
        "not-a-dict",  # invalid: not even a dict
        {"ph": "X", "ts": 0},  # valid (no name is fine)
    ]
    tracing.add_external_events(batch, tracing.RENDERER_PID)
    assert tracing._invalid_event_count == 2
    with tracing._external_events_lock:
        # Only the two valid events should have been buffered.
        assert len(tracing._external_events) == 2
    tracing.stop_and_write_trace()


def test_buffer_overflow_drops_oldest_and_records_count(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    # Stuff the buffer past the cap. Each batch is the cap-size so we go
    # well over.
    overcap = tracing.MAX_BUFFERED_EXTERNAL_EVENTS + 50
    events = [{"ph": "X", "name": f"e{i}", "ts": i} for i in range(overcap)]
    tracing.add_external_events(events, tracing.RENDERER_PID)
    with tracing._external_events_lock:
        assert len(tracing._external_events) == tracing.MAX_BUFFERED_EXTERNAL_EVENTS
    assert tracing._dropped_event_count == 50
    tracing.stop_and_write_trace()

    with open(out) as f:
        data = json.load(f)
    # A "tracing.dropped" sentinel should be present so the viewer can see
    # that some external events were dropped.
    dropped_markers = [e for e in data["traceEvents"] if e.get("name") == "tracing.dropped"]
    assert len(dropped_markers) == 1
    assert dropped_markers[0]["args"]["count"] == 50


def test_no_process_name_metadata_for_empty_source(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    # Only renderer events — no electron_main.
    tracing.add_external_events(
        [{"ph": "X", "name": "r.event", "ts": 0, "dur": 1}],
        tracing.RENDERER_PID,
    )
    tracing.stop_and_write_trace()

    with open(out) as f:
        data = json.load(f)
    process_name_pids = {e["pid"] for e in data["traceEvents"] if e.get("name") == "process_name"}
    assert tracing.RENDERER_PID in process_name_pids
    assert tracing.ELECTRON_MAIN_PID not in process_name_pids


def test_combined_output_is_valid_chrome_json(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    tracing.add_external_events(
        [{"ph": "X", "name": f"e{i}", "ts": i, "dur": 1} for i in range(20)],
        tracing.RENDERER_PID,
    )
    tracing.stop_and_write_trace()

    # The streaming writer must produce valid JSON Chrome can parse.
    with open(out) as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert isinstance(data["traceEvents"], list)
    assert len(data["traceEvents"]) >= 20


def test_atomic_write_preserves_prior_file_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A mid-write serialization failure must not clobber a pre-existing file
    at ``trace_to_path``, and must not leak a ``.tmp`` sibling."""
    out = tmp_path / "trace.json"
    prior_content = b"PRIOR_CONTENT"
    out.write_bytes(prior_content)

    tracing.start_tracing(out)
    # Buffer enough events that the streaming loop will make multiple
    # json.dumps calls (the merge now batches; shrink the batch size so
    # 5 events span >1 batch).
    monkeypatch.setattr(tracing, "_MERGE_BATCH_SIZE", 2)
    tracing.add_external_events(
        [{"ph": "X", "name": f"e{i}", "ts": i, "dur": 1} for i in range(5)],
        tracing.RENDERER_PID,
    )

    real_json_dumps = tracing.json.dumps
    call_count = {"n": 0}

    def failing_json_dumps(obj: Any, separators: tuple[str, str]) -> Any:
        # Match the call shape at ``_flush_event_batch``: ``json.dumps(batch,
        # separators=(',', ':'))``. We intercept the second call to simulate
        # a mid-stream failure after at least one batch has already been
        # written to the .tmp file.
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise ValueError("simulated serialization failure")
        return real_json_dumps(obj, separators=separators)

    monkeypatch.setattr("sculptor.utils.tracing.json.dumps", failing_json_dumps)

    with pytest.raises(ValueError, match="simulated serialization failure"):
        tracing.stop_and_write_trace()

    # Prior file content must be untouched — os.replace was never reached.
    assert out.read_bytes() == prior_content
    # No `.tmp` artifact should be left behind on partial failure.
    leftover_tmps = list(tmp_path.glob("*.tmp"))
    assert leftover_tmps == [], f"Expected no leftover .tmp files, found {leftover_tmps}"


def test_successful_write_leaves_no_tmp_file(tmp_path: Path) -> None:
    """The happy path must rename the ``.tmp`` away to the user-facing path
    and leave no sibling artifact in the destination directory."""
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)
    tracing.add_external_events(
        [{"ph": "X", "name": "renderer.boot", "ts": 0, "dur": 1}],
        tracing.RENDERER_PID,
    )
    tracing.stop_and_write_trace()

    assert out.exists()
    leftover_tmps = list(tmp_path.glob("*.tmp"))
    assert leftover_tmps == [], f"Expected no leftover .tmp files, found {leftover_tmps}"


def test_tracer_entries_uses_module_constant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The viztracer buffer cap must be driven by ``DEFAULT_TRACER_ENTRIES``.

    Pins the user-facing capture-length guarantee: at viztracer's default of
    1M entries, a Sculptor session wraps in ~1.6s of wall time at peak event
    rates, which is too short to be useful. The module constant raises this
    so realistic dev sessions fit inside the buffer; this test makes sure
    a future refactor doesn't silently drop the override and revert to the
    library default.
    """
    monkeypatch.setattr(tracing, "DEFAULT_TRACER_ENTRIES", 12_345)
    tracing.start_tracing(tmp_path / "out.json")
    try:
        assert tracing._tracer.tracer_entries == 12_345
    finally:
        tracing.stop_and_write_trace()


def test_concurrent_overflow_counts_accurately(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins the threading-safety fix in ``add_external_events``.

    The endpoint runs on FastAPI worker threads, so concurrent batches can
    race on the module-level counters. Pre-fix, ``+=`` on a Python int
    outside ``_external_events_lock`` could silently lose counts when two
    threads read the same value and each wrote ``n + overflow``, dropping
    one batch's contribution. This test fans out many concurrent
    overflow-triggering batches and asserts the counters add up exactly.
    """
    # Shrink the cap so the test is fast — the race is structural and
    # surfaces at any cap. The autouse fixture clears the buffer between
    # cases, but we also need to set up tracing so ``add_external_events``
    # is not a no-op.
    monkeypatch.setattr(tracing, "MAX_BUFFERED_EXTERNAL_EVENTS", 100)
    out = tmp_path / "trace.json"
    tracing.start_tracing(out)

    n_threads = 80
    batch_size = 50
    # First event in each batch is intentionally invalid (missing required
    # keys) so we also exercise the ``_invalid_event_count`` mutation under
    # contention. Remaining events are valid.
    batches: list[list[dict[str, Any]]] = []
    for thread_idx in range(n_threads):
        batch: list[dict[str, Any]] = [{"name": "bad"}]  # invalid: missing ph/ts
        batch.extend({"ph": "X", "name": f"t{thread_idx}-e{i}", "ts": i, "dur": 1} for i in range(batch_size - 1))
        batches.append(batch)

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = [pool.submit(tracing.add_external_events, batch, tracing.RENDERER_PID) for batch in batches]
        for f in futures:
            f.result()

    # Conservation: every valid event submitted either sits in the buffer or
    # was counted as a drop. A race that lost overflow bumps would make the
    # left-hand side smaller than the right-hand side.
    with tracing._external_events_lock:
        buffered_now = len(tracing._external_events)
        dropped_now = tracing._dropped_event_count
        invalid_now = tracing._invalid_event_count
    total_valid_submitted = n_threads * (batch_size - 1)
    assert buffered_now + dropped_now == total_valid_submitted
    assert buffered_now == tracing.MAX_BUFFERED_EXTERNAL_EVENTS
    assert dropped_now == total_valid_submitted - tracing.MAX_BUFFERED_EXTERNAL_EVENTS
    # One invalid event per batch, no losses.
    assert invalid_now == n_threads

    tracing.stop_and_write_trace()


def test_concurrent_start_creates_one_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins the session-lock fix in ``start_tracing``.

    The runtime trace-control endpoints run on FastAPI worker threads, so two
    ``POST /api/v1/trace/start`` calls can race the ``_tracer is None`` check. Without
    ``_trace_session_lock`` both threads pass the guard and each builds a
    ``VizTracer``, leaking the first. A counting fake (which sleeps before the
    module assigns ``_tracer``, widening the race window) asserts exactly one
    instance is ever constructed under concurrent starts.
    """
    instances: list[Any] = []

    class _CountingTracer:
        def __init__(self, *, output_file: str, **_kwargs: Any) -> None:
            # Delay before returning so that, absent the lock, every concurrent
            # caller would observe `_tracer is None` and construct. With the
            # lock, only the first caller reaches here.
            time.sleep(0.02)
            instances.append(self)
            self._output_file = output_file

        def start(self) -> None: ...

        def stop(self) -> None: ...

        def save(self) -> None:
            Path(self._output_file).write_text('{"traceEvents": []}')

    monkeypatch.setattr("viztracer.VizTracer", _CountingTracer)

    out = tmp_path / "trace.json"
    n_threads = 8
    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = [pool.submit(tracing.start_tracing, out) for _ in range(n_threads)]
        for f in futures:
            f.result()

    assert len(instances) == 1, f"expected exactly one VizTracer under concurrent start, got {len(instances)}"
    assert tracing._tracer is instances[0]

    tracing.stop_and_write_trace()


def test_external_batch_during_flush_is_not_buffered(tmp_path: Path) -> None:
    """A /api/v1/trace/batch arriving mid-flush must be dropped, not buffered.

    stop_and_write_trace holds the session lock across the flush, so the trace
    stays "armed" (path set, `is_tracing_enabled()` true) until the very end —
    which is what keeps a racing start at the 409 gate. But that also means
    add_external_events' cheap `_trace_to_path is None` fast-path does NOT
    short-circuit during the flush. The `_external_events_accepting` flag (flipped
    False under `_external_events_lock` at snapshot time) is what stops a late
    batch from buffering into the just-finished session and leaking into the
    next. This reproduces that mid-disarm window directly: path still set, but no
    longer accepting.
    """
    tracing._trace_to_path = tmp_path / "x.json"  # so the fast-path does not fire
    tracing._external_events_accepting = False  # snapshot already taken; disarming

    tracing.add_external_events([{"ph": "X", "name": "late", "ts": 0}], tracing.RENDERER_PID)

    with tracing._external_events_lock:
        assert tracing._external_events == [], "late batch must be dropped, not buffered into a dead session"


def test_external_batch_buffered_while_accepting(tmp_path: Path) -> None:
    """Sanity counterpart: while a session is armed and accepting, batches buffer
    as before (the new flag gate doesn't reject the happy path)."""
    tracing.start_tracing(tmp_path / "out.json")
    tracing.add_external_events([{"ph": "X", "name": "live", "ts": 0}], tracing.RENDERER_PID)
    with tracing._external_events_lock:
        assert len(tracing._external_events) == 1
    tracing.stop_and_write_trace()
