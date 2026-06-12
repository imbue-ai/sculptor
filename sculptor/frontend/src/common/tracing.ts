/** Frontend tracing collector.
 *
 * Activated when the backend inlines ``window.__SCULPTOR_TRACING__ = {enabled:
 * true}`` into the served HTML (see ``serve_static`` in ``web/app.py``). When
 * disabled the public functions are inert — no PerformanceObserver, no fetch
 * intercepts, no timers — so the production cost is near zero.
 *
 * When enabled, a single PerformanceObserver covers ``mark`` and ``resource``
 * entry types. That single observer is intentionally everything we install:
 * we do not monkey-patch ``fetch`` / ``XMLHttpRequest`` / ``WebSocket``
 * globals. Resource Timing already covers HTTP/XHR/WS handshake timings, and
 * application-level WebSocket send/recv points are instrumented by hand with
 * ``performance.mark()`` at the wrapper layer in ``useWebsocket``.
 *
 * Collected entries are converted to Chrome JSON trace events and flushed to
 * the backend in batches every few seconds, plus on ``beforeunload``. The
 * backend tags each batch with a synthetic ``pid`` (renderer vs Electron
 * main) so the sources appear as separate processes in the Perfetto UI.
 */

const FLUSH_INTERVAL_MS = 3000;

// Hard cap on the in-memory pending-event buffer. If the backend is gone or
// the POST is being rejected, we drop oldest events past the
// cap and emit a single sentinel marker so the viewer can see that data was
// lost. Without this, a failing backend turns the renderer into a memory
// leak that grows until the tab dies.
const MAX_PENDING_EVENTS = 20_000;

// window.__SCULPTOR_TRACING__ is declared in globals.d.ts.

type ChromeEvent = Record<string, unknown>;

let isEnabled = false;
let pendingEvents: Array<ChromeEvent> = [];
let droppedEventCount = 0;
let baseUrlForFlush: string = "";
// One-shot log gate. The first flush failure (network error or non-2xx
// response) emits a single ``console.warn`` so a developer debugging
// "events disappearing" has a thread to pull; subsequent failures are
// silent so a persistently failing backend doesn't fill the console.
let hasLoggedFlushFailure = false;

const toMicroseconds = (milliseconds: number): number => Math.round(milliseconds * 1000);

const markEntryToEvent = (entry: PerformanceMark): ChromeEvent => ({
  ph: "i", // "instant"
  name: entry.name,
  cat: "mark",
  ts: toMicroseconds(entry.startTime),
  s: "t", // thread-scoped instant
});

const measureEntryToEvent = (entry: PerformanceMeasure): ChromeEvent => ({
  ph: "X", // "complete"
  name: entry.name,
  cat: "measure",
  ts: toMicroseconds(entry.startTime),
  dur: toMicroseconds(entry.duration),
});

const resourceEntryToEvent = (entry: PerformanceResourceTiming): ChromeEvent => ({
  ph: "X",
  name: entry.name,
  cat: `resource.${entry.initiatorType}`,
  ts: toMicroseconds(entry.startTime),
  dur: toMicroseconds(entry.duration),
  args: {
    initiator: entry.initiatorType,
    transferSize: entry.transferSize,
    encodedBodySize: entry.encodedBodySize,
  },
});

const entryToEvent = (entry: PerformanceEntry): ChromeEvent | null => {
  if (entry.entryType === "mark") return markEntryToEvent(entry as PerformanceMark);
  if (entry.entryType === "measure") return measureEntryToEvent(entry as PerformanceMeasure);
  if (entry.entryType === "resource") return resourceEntryToEvent(entry as PerformanceResourceTiming);
  return null;
};

const pushEvent = (event: ChromeEvent): void => {
  pendingEvents.push(event);
  applyBufferCap();
};

const applyBufferCap = (): void => {
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

const flush = (useBeacon: boolean = false): void => {
  if (pendingEvents.length === 0 && droppedEventCount === 0) return;
  const batch = pendingEvents;
  if (droppedEventCount > 0) {
    batch.push(droppedMarker(droppedEventCount));
    droppedEventCount = 0;
  }
  pendingEvents = [];
  const payload = JSON.stringify({ source: "renderer", events: batch });
  const url = `${baseUrlForFlush}/api/v1/trace/batch`;
  // On beforeunload, sendBeacon survives the navigation; regular fetch is
  // cancelled. During normal flushes we prefer fetch because it can re-queue
  // events on failure (kept in-memory in pendingEvents).
  if (useBeacon && navigator.sendBeacon) {
    try {
      navigator.sendBeacon(url, new Blob([payload], { type: "application/json" }));
    } catch {
      // ignored — last-ditch flush, nothing to do
    }
    return;
  }
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true,
  })
    .then((response) => {
      // A non-2xx response resolves the fetch promise successfully, but the
      // backend didn't accept the batch. Treat it the same as a network
      // failure so the events get re-queued in the catch handler below.
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
    })
    .catch((error: unknown) => {
      // On failure, put the events back so the next flush retries. New events
      // may have been pushed during the await; the concat re-orders by
      // batch-then-new (chronological), then we re-apply the cap so a
      // persistently failing backend cannot grow this list unboundedly.
      pendingEvents = batch.concat(pendingEvents);
      applyBufferCap();
      if (!hasLoggedFlushFailure) {
        hasLoggedFlushFailure = true;
        const detail = error instanceof Error ? error.message : String(error);
        console.warn(`[tracing] flush failed (${detail}), requeued ${batch.length} events`);
      }
    });
};

/** Initialize the renderer-side tracing collector. Call once at boot, after
 * ``configureClient`` has resolved the backend base URL. No-op when tracing
 * is not enabled by the backend. */
export const initializeTracing = (backendBaseUrl: string): void => {
  if (!window.__SCULPTOR_TRACING__?.enabled) return;
  isEnabled = true;
  baseUrlForFlush = backendBaseUrl;

  console.log("[tracing] Tracing enabled — flushing renderer events to backend");

  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      const event = entryToEvent(entry);
      if (event !== null) pushEvent(event);
    }
  });
  // ``buffered: true`` picks up entries created BEFORE the observer was
  // registered (e.g. resource timings from the initial page load).
  observer.observe({ type: "mark", buffered: true });
  observer.observe({ type: "measure", buffered: true });
  observer.observe({ type: "resource", buffered: true });

  // The interval handle is intentionally not retained: the renderer process
  // lives as long as the tab, and `beforeunload` covers shutdown.
  setInterval(() => flush(false), FLUSH_INTERVAL_MS);
  window.addEventListener("beforeunload", () => flush(true));
};

/** Hand-placed instant span. No-op when tracing is disabled. Use at known
 * hotspots (route changes, key effects, expensive helpers) so spans show up
 * in the Perfetto UI under friendly names. */
export const traceMark = (name: string): void => {
  if (!isEnabled) return;
  try {
    performance.mark(name);
  } catch (e) {
    // `performance.mark` only throws DOMException (for User Timing
    // unavailability) in supported browsers. Anything else here is a
    // programming bug and should be visible — re-throw so it surfaces.
    if (!(e instanceof DOMException)) throw e;
  }
};
