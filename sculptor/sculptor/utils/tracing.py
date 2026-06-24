"""Perfetto / viztracer tracing module.

Activated only when `--trace-to=<path>` is passed on the CLI. When inactive,
the module's import is cheap and no functions in here do work.

Flow:
1. ``start_tracing(path)`` is called very early from ``cli/main.py`` (before
   the heavy ``cli/app`` import), so viztracer captures backend imports too.
2. ``add_external_events(...)`` buffers Chrome-JSON batches received over HTTP
   from the renderer and from the Electron main process. Each batch is tagged
   with a synthetic ``pid`` distinguishing it from the real backend ``pid``.
3. ``stop_and_write_trace()`` is called on backend shutdown. It stops
   viztracer, reads viztracer's native output, merges in the buffered
   external events, and writes the combined Chrome-JSON file at the
   user-chosen path.

Memory: the merge stream-writes events one at a time so we only ever hold
two copies of any single event in memory (the parsed list from viztracer
plus the one being serialized). The external-event buffer is capped (see
``MAX_BUFFERED_EXTERNAL_EVENTS``) so a flush-loop client cannot grow the
backend heap unboundedly.

Concurrency: ``add_external_events`` runs on FastAPI worker threads (one per
concurrent POST to ``/api/v1/trace/batch``). All mutations and reads of
``_external_events``, ``_dropped_event_count``, and ``_invalid_event_count``
must happen under ``_external_events_lock`` — ``+=`` on a Python int is not
atomic across threads, so unprotected mutations would silently lose counts
under concurrent overflow.
"""

import itertools
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from typing import IO
from typing import Iterable
from typing import Sequence

# Synthetic PIDs for non-backend sources. Chosen well above the typical OS
# pid range so they cannot collide with the real backend pid or its children.
RENDERER_PID = 9_000_001
ELECTRON_MAIN_PID = 9_000_002

# Cap on the in-memory external-event buffer. Above this size we drop oldest
# events and emit a single sentinel marker so the viewer can see that data
# was dropped. At ~150 bytes/event this caps the buffer at ~15 MB which is
# acceptable as backpressure on a dev-only tool.
MAX_BUFFERED_EXTERNAL_EVENTS = 100_000

# Cap on viztracer's in-memory ring buffer. Above this size the buffer wraps
# and the oldest events are evicted. Measured event rate during Sculptor boot
# peaks around 600k events/sec (import-time + alembic + pydantic schema gen);
# the steady-state interactive rate is much lower. 50M entries gives roughly
# 80 seconds of capture before wrap — long enough to cover a typical
# "boot + observe one interaction" dev session. The C-side cost is ~50
# bytes/entry, so this caps viztracer's resident memory at ~2.5 GB, which is
# fine for a developer workstation and well below what the merge step would
# materialize anyway.
DEFAULT_TRACER_ENTRIES = 50_000_000

# Smaller default ring buffer for ad-hoc tracing armed at runtime (via the
# trace-control HTTP endpoint / `sculpt trace start`) rather than at boot.
# Runtime arming targets steady-state interactive work, whose event rate is
# far below the boot peak the 50M buffer is sized for, so a fifth of the
# entries (~500 MB) still covers a generous capture window while keeping the
# resident footprint reasonable on a machine running a real workload.
DEFAULT_ADHOC_TRACER_ENTRIES = 10_000_000

# Required keys on every Chrome-JSON event we accept. Events missing either
# field are dropped; the rest of the batch is still ingested. This is cheap
# insurance against a renderer regression silently corrupting every trace
# file for a week.
_REQUIRED_EVENT_KEYS = ("ph", "ts")

# Number of events to bundle into a single ``json.dumps`` call during the
# final merge. A per-event ``json.dump(event, f)`` loop pays the encoder's
# Python-level entry/exit cost on every iteration, which dominates wall time
# at million-event scale (measured: ~7s/1M events). Bundling drops the per-
# call overhead so the merge becomes I/O-bound. 4096 is the smallest batch
# at which the per-call overhead disappears in our microbenchmark; larger
# batches give no further win and grow the transient string buffer.
_MERGE_BATCH_SIZE = 4096

_trace_to_path: Path | None = None
_tracer: Any = None
_internal_trace_path: Path | None = None
_external_events_lock = Lock()
_external_events: list[dict[str, Any]] = []
_dropped_event_count = 0
_invalid_event_count = 0


@dataclass(frozen=True)
class TraceWriteResult:
    """Outcome of a completed trace flush, returned by ``stop_and_write_trace``.

    ``path`` is the file the combined Chrome-JSON trace was written to.
    The counts are the number of backend (viztracer) and external (renderer /
    Electron-main) events the file contains, exposed so the trace-control HTTP
    endpoint can report how much was captured without re-reading the file.
    """

    path: Path
    backend_event_count: int
    external_event_count: int


def is_tracing_enabled() -> bool:
    return _trace_to_path is not None


def get_trace_to_path() -> Path | None:
    return _trace_to_path


def get_buffered_external_event_count() -> int:
    """Number of external (renderer / Electron-main) events currently buffered
    and awaiting the next flush. Read under the lock so the count is consistent
    with concurrent ``add_external_events`` writers."""
    with _external_events_lock:
        return len(_external_events)


def start_tracing(output_path: Path, tracer_entries: int | None = None) -> None:
    """Start viztracer, writing the combined trace to ``output_path`` when it is
    later stopped. ``tracer_entries`` sizes viztracer's in-memory ring buffer;
    ``None`` uses ``DEFAULT_TRACER_ENTRIES`` (resolved at call time so tests can
    monkeypatch the constant).

    Idempotent — a second call while a trace is already running is a no-op (it
    does NOT change the path or buffer size). After ``stop_and_write_trace``
    has flushed and torn down a session, calling this again arms a fresh one,
    which is what makes the runtime arm/disarm cycle (`sculpt trace start` then
    `stop` then `start`) work.
    """
    global _trace_to_path, _tracer, _internal_trace_path
    if _tracer is not None:
        return
    from viztracer import VizTracer

    if tracer_entries is None:
        tracer_entries = DEFAULT_TRACER_ENTRIES
    _trace_to_path = output_path.resolve()
    tmp_dir = Path(tempfile.mkdtemp(prefix="sculptor_viztrace_"))
    _internal_trace_path = tmp_dir / "viztracer.json"
    _tracer = VizTracer(
        output_file=str(_internal_trace_path),
        tracer_entries=tracer_entries,
        log_func_args=False,
        log_print=False,
        minimize_memory=True,
        process_name="sculptor_backend",
    )
    _tracer.start()


def add_external_events(events: Sequence[dict[str, Any]], source_pid: int) -> None:
    """Buffer Chrome-JSON events from a non-backend source. Tags each event
    with the supplied synthetic ``pid``. Drops events missing required Chrome
    JSON fields and applies a hard cap on the buffer size (oldest first) so a
    flush-loop client cannot grow the backend heap unboundedly.

    Called from FastAPI worker threads — see the module docstring's
    Concurrency section. The per-event validation is pure CPU work and runs
    outside the lock; only the buffer mutation and counter bumps need it.

    Mutates each event dict in place to set ``pid`` (and ``tid`` if absent).
    Callers should not rely on the input dicts being untouched after the
    call. In practice the only caller is the Pydantic-parsed POST body,
    which is not re-read after this function returns."""
    global _dropped_event_count, _invalid_event_count
    if _trace_to_path is None:
        return

    valid_events: list[dict[str, Any]] = []
    invalid_count = 0
    for event in events:
        if not isinstance(event, dict) or not all(k in event for k in _REQUIRED_EVENT_KEYS):
            invalid_count += 1
            continue
        event["pid"] = source_pid
        if "tid" not in event:
            event["tid"] = source_pid
        valid_events.append(event)

    if not valid_events and invalid_count == 0:
        return

    with _external_events_lock:
        _invalid_event_count += invalid_count
        if valid_events:
            _external_events.extend(valid_events)
            overflow = len(_external_events) - MAX_BUFFERED_EXTERNAL_EVENTS
            if overflow > 0:
                del _external_events[:overflow]
                _dropped_event_count += overflow


def _process_name_metadata(pid: int, name: str) -> dict[str, Any]:
    return {
        "ph": "M",
        "pid": pid,
        "tid": pid,
        "name": "process_name",
        "args": {"name": name},
    }


def _dropped_marker_event(dropped_count: int, invalid_count: int) -> dict[str, Any]:
    """Sentinel instant event so the viewer can see that some external events
    were dropped due to buffer overflow. Tagged to the renderer pid because
    we don't track per-source overflow; the count is total across sources.

    Both counts are passed in as snapshots — the caller is responsible for
    reading them under ``_external_events_lock`` so concurrent writers can't
    bump the counters out from under us between snapshot and use."""
    return {
        "ph": "i",
        "pid": RENDERER_PID,
        "tid": RENDERER_PID,
        "name": "tracing.dropped",
        "cat": "tracing",
        "ts": 0,
        "s": "g",
        "args": {"count": dropped_count, "invalid": invalid_count},
    }


def _stream_events_batched(events: Iterable[dict[str, Any]], f: IO[str]) -> None:
    """Stream events to ``f`` as comma-separated JSON, batched for speed.

    Equivalent in output to a per-event ``json.dump(event, f)`` loop but pays
    the JSON encoder's Python-level entry cost once per batch instead of once
    per event. At million-event scale the batched form is ~8x faster on a
    Sculptor trace; the per-event form was the dominant cost of the merge
    step and what was driving teardown over the test-harness SIGKILL budget.

    Caller is responsible for emitting the opening ``[`` and closing ``]``;
    this helper writes only the elements (no surrounding brackets, no
    trailing comma).
    """
    batch: list[dict[str, Any]] = []
    is_first_batch = True
    for event in events:
        batch.append(event)
        if len(batch) >= _MERGE_BATCH_SIZE:
            _flush_event_batch(batch, f, is_first_batch)
            is_first_batch = False
            batch.clear()
    if batch:
        _flush_event_batch(batch, f, is_first_batch)


def _flush_event_batch(batch: Sequence[dict[str, Any]], f: IO[str], is_first_batch: bool) -> None:
    # ``json.dumps`` on a list produces ``[e1,e2,...]``; stripping the outer
    # brackets gives a JSON-array-element fragment we can splice between
    # ``[`` and ``]`` written by the caller. ``separators=(',', ':')`` matches
    # the compact form the previous per-event ``json.dump`` produced.
    payload = json.dumps(batch, separators=(",", ":"))[1:-1]
    if not is_first_batch:
        f.write(",")
    f.write(payload)


def stop_and_write_trace() -> TraceWriteResult | None:
    """Stop viztracer, merge with buffered external events, and write the
    combined Chrome-JSON file to the configured trace path. Returns a
    ``TraceWriteResult`` describing the written file, or ``None`` if no trace
    was active.

    The output is stream-written one event at a time rather than building a
    single dict in memory, so peak memory at exit is just viztracer's parsed
    events plus one in-flight serializer call.

    After a successful (or failed) flush the module's trace state is reset to
    the disarmed state, so a subsequent ``start_tracing`` arms a fresh session.
    This is what makes runtime arm/disarm cycling work; it also means the
    shutdown-time caller must read ``get_trace_to_path()`` BEFORE calling this
    (or use the returned result), since the global is cleared here.
    """
    global _trace_to_path, _tracer, _internal_trace_path, _dropped_event_count, _invalid_event_count
    trace_to_path = _trace_to_path
    tracer = _tracer
    internal_trace_path = _internal_trace_path
    if trace_to_path is None or tracer is None or internal_trace_path is None:
        return None

    try:
        tracer.stop()
        tracer.save()

        with open(internal_trace_path) as f:
            viztracer_data = json.load(f)
        viztracer_events = viztracer_data.get("traceEvents", [])

        with _external_events_lock:
            buffered = list(_external_events)
            _external_events.clear()
            dropped_snapshot = _dropped_event_count
            invalid_snapshot = _invalid_event_count

        seen_synthetic_pids = {e["pid"] for e in buffered}
        metadata_events: list[dict[str, Any]] = []
        if RENDERER_PID in seen_synthetic_pids:
            metadata_events.append(_process_name_metadata(RENDERER_PID, "renderer"))
        if ELECTRON_MAIN_PID in seen_synthetic_pids:
            metadata_events.append(_process_name_metadata(ELECTRON_MAIN_PID, "electron_main"))
        if dropped_snapshot > 0 or invalid_snapshot > 0:
            metadata_events.append(_dropped_marker_event(dropped_snapshot, invalid_snapshot))

        trace_to_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: stream to a sibling `.tmp` file, then `os.replace` into
        # place on success. A mid-write serialization failure must not leave a
        # truncated file at the user-facing path, and any prior file there
        # must remain untouched.
        tmp_path = trace_to_path.parent / (trace_to_path.name + ".tmp")
        try:
            with open(tmp_path, "w") as f:
                f.write('{"traceEvents":[')
                _stream_events_batched(itertools.chain(viztracer_events, metadata_events, buffered), f)
                f.write("]}")
            os.replace(tmp_path, trace_to_path)
        finally:
            # On success, the tmp file has been renamed away and this is a
            # no-op. On failure, drop the partial `.tmp` so we don't leak it.
            tmp_path.unlink(missing_ok=True)
        return TraceWriteResult(
            path=trace_to_path,
            backend_event_count=len(viztracer_events),
            external_event_count=len(buffered),
        )
    finally:
        # Always clean up the viztracer temp dir, even on partial-write
        # failure. The user-facing trace file at trace_to_path is intentionally
        # NOT cleaned up — that's the artifact they came here for.
        shutil.rmtree(internal_trace_path.parent, ignore_errors=True)
        # Disarm: drop references to the stopped tracer and clear the path so
        # the module is ready to arm a fresh session. Dropping the only
        # reference to the VizTracer also lets it be garbage-collected; the
        # next start_tracing builds a new instance (viztracer's global
        # __viz_tracer__ pointer is simply overwritten).
        _tracer = None
        _trace_to_path = None
        _internal_trace_path = None
        _dropped_event_count = 0
        _invalid_event_count = 0
