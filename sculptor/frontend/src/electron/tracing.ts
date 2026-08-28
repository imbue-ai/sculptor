/** Electron main process tracing collector.
 *
 * Activates when ``--trace-to=<path>`` (or ``--sculptor=--trace-to=<path>``,
 * the user-facing form that also forwards the flag to the spawned backend)
 * is found on the Electron command line. When disabled the exports are
 * inert.
 *
 * Buffers Chrome-JSON events in memory and flushes them to the backend's
 * ``POST /api/v1/trace/batch`` endpoint on the same cadence as the renderer.
 * The backend tags incoming batches with the synthetic Electron-main pid and
 * folds them into the combined trace at process exit.
 */

import { performance } from "node:perf_hooks";

const FLUSH_INTERVAL_MS = 3000;
const TRACE_TO_PREFIX = "--trace-to=";
const SCULPTOR_TRACE_TO_PREFIX = "--sculptor=--trace-to=";

// Hard cap on the in-memory pending-event buffer; see the matching constant
// in common/perf/tracing.ts for the rationale. Electron main produces fewer
// events than the renderer, but we still need the cap so a flush loop
// against a dead backend cannot grow this list unboundedly.
const MAX_PENDING_EVENTS = 20_000;

// SIGTERM→SIGKILL budget for the backend when --trace-to is active. The
// backend's lifespan teardown calls viztracer.save() + json.load() + a merge
// pass; sized as the time to drain the entire DEFAULT_TRACER_ENTRIES buffer
// with a safety factor. Mirrors _TEARDOWN_TIMEOUT_SECONDS_WITH_TRACE in
// sculptor/sculptor/testing/sculptor_instance.py so the Electron shutdown
// matches the integration-test harness — without this the trace file is
// SIGKILLed away before viztracer finishes loading even a moderate session.
const TRACING_TEARDOWN_GRACE_PERIOD_MS = 300_000;

type ChromeEvent = Record<string, unknown>;

let traceToPath: string | null = null;
let pendingEvents: Array<ChromeEvent> = [];
let droppedEventCount = 0;
let backendUrlForFlush: string | null = null;
let flushTimer: NodeJS.Timeout | null = null;
// One-shot log gate. The first flush failure (network error or non-2xx
// response) emits a single ``console.warn`` so a developer debugging
// "events disappearing" has a thread to pull; subsequent failures are
// silent so a persistently failing backend doesn't fill the console.
let hasLoggedFlushFailure = false;

const toMicroseconds = (ms: number): number => Math.round(ms * 1000);

const pushEvent = (event: ChromeEvent): void => {
  pendingEvents.push(event);
  const overflow = pendingEvents.length - MAX_PENDING_EVENTS;
  if (overflow > 0) {
    pendingEvents.splice(0, overflow);
    droppedEventCount += overflow;
  }
};

const droppedMarker = (count: number): ChromeEvent => ({
  ph: "i",
  cat: "tracing",
  name: "tracing.dropped",
  ts: 0,
  s: "g",
  args: { count },
});

/** Find ``--trace-to=<path>`` or the prefixed ``--sculptor=--trace-to=<path>``
 * variant in the supplied argv. The prefixed form is what users actually
 * type (it's the same arg-forwarding mechanism used for all backend flags).
 * The unprefixed form is supported for direct Electron invocations. */
export const parseTraceToArg = (argv: ReadonlyArray<string>): string | null => {
  for (const arg of argv) {
    if (arg.startsWith(SCULPTOR_TRACE_TO_PREFIX)) {
      return arg.slice(SCULPTOR_TRACE_TO_PREFIX.length);
    }

    if (arg.startsWith(TRACE_TO_PREFIX)) {
      return arg.slice(TRACE_TO_PREFIX.length);
    }
  }
  return null;
};

export const isTracingEnabled = (): boolean => traceToPath !== null;

/** Pick the SIGTERM→SIGKILL grace period the Electron main process should
 * give the backend when tearing it down. Returns the extended budget when
 * --trace-to is in effect (the backend's lifespan teardown writes the trace
 * file inline and can take a long time on a full buffer), the supplied
 * default otherwise. */
export const tracingTeardownGracePeriodMs = (defaultMs: number): number =>
  isTracingEnabled() ? TRACING_TEARDOWN_GRACE_PERIOD_MS : defaultMs;

export const initializeElectronTracing = (path: string): void => {
  traceToPath = path;
  console.log(`[tracing] Tracing enabled, output -> ${path}`);
};

export const traceMark = (name: string): void => {
  if (!traceToPath) return;
  pushEvent({
    ph: "i",
    name,
    cat: "mark",
    ts: toMicroseconds(performance.now()),
    s: "t",
  });
};

/** Wire the collector to a backend URL once it's known and start the periodic
 * flush timer. Must be called exactly once per process lifetime; subsequent
 * calls or null-URL calls are silently ignored. */
export const setBackendUrlForTracing = (url: string | null): void => {
  if (!traceToPath || backendUrlForFlush !== null || url === null) return;
  backendUrlForFlush = url;
  flushTimer = setInterval(() => {
    void flush();
  }, FLUSH_INTERVAL_MS);
};

const flush = async (): Promise<void> => {
  if (!traceToPath || !backendUrlForFlush) return;
  if (pendingEvents.length === 0 && droppedEventCount === 0) return;
  const batch = pendingEvents;
  if (droppedEventCount > 0) {
    batch.push(droppedMarker(droppedEventCount));
    droppedEventCount = 0;
  }
  pendingEvents = [];
  try {
    const response = await fetch(`${backendUrlForFlush}/api/v1/trace/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "electron_main", events: batch }),
    });
    // A non-2xx response resolves the fetch promise successfully, but the
    // backend didn't accept the batch. Throw so the catch block re-queues
    // the events the same way it does for network errors.
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error: unknown) {
    // Put the batch back so the next attempt retries. New events may have
    // been pushed during the await; concat batch-then-new keeps chronological
    // order, then re-apply the cap so a persistently failing backend cannot
    // grow this list unboundedly.
    pendingEvents = batch.concat(pendingEvents);
    const overflow = pendingEvents.length - MAX_PENDING_EVENTS;
    if (overflow > 0) {
      pendingEvents.splice(0, overflow);
      droppedEventCount += overflow;
    }

    if (!hasLoggedFlushFailure) {
      hasLoggedFlushFailure = true;
      const detail = error instanceof Error ? error.message : String(error);
      console.warn(`[tracing] flush failed (${detail}), requeued ${batch.length} events`);
    }
  }
};

/** Best-effort async flush before the backend process goes away. The backend
 * writes the combined trace file at its own exit, so anything we miss here
 * is simply absent from the renderer/main half of the trace. */
export const flushTracingBeforeExit = async (): Promise<void> => {
  await flush();
  if (flushTimer) {
    clearInterval(flushTimer);
    flushTimer = null;
  }
};
