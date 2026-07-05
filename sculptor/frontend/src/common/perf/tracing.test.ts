/** Tests for the renderer-side tracing collector.
 *
 * The module under test holds mutable module-level state (``isEnabled``,
 * ``pendingEvents``, etc.), so each test imports it via ``vi.resetModules()``
 * + dynamic ``await import()`` for an isolated snapshot. Fetches, the
 * PerformanceObserver, and ``performance.mark`` are all stubbed so the tests
 * can drive the flush/retry paths without depending on the browser's
 * scheduling of real performance entries.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as TracingModuleNamespace from "./tracing";

type ChromeEvent = Record<string, unknown>;
type ObserverCallback = (list: { getEntries: () => Array<PerformanceEntry> }) => void;
type TracingModule = typeof TracingModuleNamespace;

const BASE_URL = "https://backend.invalid";
const TRACE_ENDPOINT = `${BASE_URL}/api/v1/trace/batch`;

/** Captures the most recent PerformanceObserver callback so tests can invoke
 * it directly with synthetic entries. The real observer would fire it when
 * the browser dispatched matching ``mark``/``measure``/``resource`` entries;
 * in jsdom we drive it ourselves. */
let observerCallback: ObserverCallback | null = null;

const makeMarkEntry = (name: string, startTime = 0): PerformanceEntry =>
  ({
    name,
    entryType: "mark",
    startTime,
    duration: 0,
    toJSON: () => ({}),
  }) as unknown as PerformanceEntry;

const setupTracingEnabledEnv = (): void => {
  observerCallback = null;
  // PerformanceObserver is not implemented by jsdom; provide a stub that
  // captures the callback and turns observe()/disconnect() into no-ops.
  class MockPerformanceObserver {
    constructor(callback: ObserverCallback) {
      observerCallback = callback;
    }
    observe(): void {}
    disconnect(): void {}
  }
  vi.stubGlobal("PerformanceObserver", MockPerformanceObserver);
  vi.stubGlobal("performance", { mark: vi.fn(), measure: vi.fn(), now: (): number => 0 });
  vi.stubGlobal("fetch", vi.fn());
  vi.stubGlobal("navigator", { sendBeacon: vi.fn(() => true) });
  (window as unknown as { __SCULPTOR_TRACING__?: { enabled: boolean } }).__SCULPTOR_TRACING__ = { enabled: true };
};

const loadTracing = async (): Promise<TracingModule> => {
  vi.resetModules();
  return await import("./tracing");
};

const flushPromises = async (): Promise<void> => {
  // Yield to the microtask queue so chained ``.then/.catch`` handlers on the
  // mocked fetch settle before assertions run.
  await Promise.resolve();
  await Promise.resolve();
};

const getLastFetchBody = (fetchMock: ReturnType<typeof vi.fn>): { events: Array<ChromeEvent> } => {
  const calls = fetchMock.mock.calls;
  const last = calls[calls.length - 1];
  return JSON.parse(last[1].body as string) as { events: Array<ChromeEvent> };
};

describe("tracing", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete (window as unknown as { __SCULPTOR_TRACING__?: unknown }).__SCULPTOR_TRACING__;
    observerCallback = null;
  });

  it("is a no-op when window.__SCULPTOR_TRACING__ is absent", async () => {
    const observerSpy = vi.fn();
    vi.stubGlobal("PerformanceObserver", observerSpy);
    vi.stubGlobal("performance", { mark: vi.fn() });
    vi.stubGlobal("fetch", vi.fn());
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");

    const { initializeTracing, traceMark } = await loadTracing();
    initializeTracing(BASE_URL);
    traceMark("never-fires");

    expect(observerSpy).not.toHaveBeenCalled();
    expect(setIntervalSpy).not.toHaveBeenCalled();
    expect(globalThis.performance.mark as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
    expect(globalThis.fetch as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
  });

  it("is a no-op when window.__SCULPTOR_TRACING__ is explicitly disabled", async () => {
    const observerSpy = vi.fn();
    vi.stubGlobal("PerformanceObserver", observerSpy);
    vi.stubGlobal("performance", { mark: vi.fn() });
    (window as unknown as { __SCULPTOR_TRACING__?: { enabled: boolean } }).__SCULPTOR_TRACING__ = { enabled: false };

    const { initializeTracing, traceMark } = await loadTracing();
    initializeTracing(BASE_URL);
    traceMark("never-fires");

    expect(observerSpy).not.toHaveBeenCalled();
    expect(globalThis.performance.mark as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
  });

  it("calls performance.mark when enabled but skips it when disabled", async () => {
    // Disabled path: traceMark must not touch performance.mark even if it
    // exists, otherwise we'd pay the cost (and create entries) on every
    // production page load.
    vi.stubGlobal("performance", { mark: vi.fn() });
    const { traceMark: traceMarkDisabled } = await loadTracing();
    traceMarkDisabled("disabled-call");
    expect(globalThis.performance.mark as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();

    // Enabled path: a single call to traceMark forwards to performance.mark.
    setupTracingEnabledEnv();
    const { initializeTracing, traceMark } = await loadTracing();
    initializeTracing(BASE_URL);
    traceMark("hello");
    expect(globalThis.performance.mark as ReturnType<typeof vi.fn>).toHaveBeenCalledWith("hello");
  });

  it("flushes pending events to /api/v1/trace/batch and clears the buffer on success", async () => {
    setupTracingEnabledEnv();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { initializeTracing } = await loadTracing();
    initializeTracing(BASE_URL);
    observerCallback!({ getEntries: () => [makeMarkEntry("first"), makeMarkEntry("second")] });

    vi.advanceTimersByTime(3000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(TRACE_ENDPOINT);
    const body = JSON.parse(init.body as string) as { source: string; events: Array<ChromeEvent> };
    expect(body.source).toBe("renderer");
    expect(body.events.map((event) => event.name)).toEqual(["first", "second"]);

    // After the successful fetch resolves, the next flush tick must send
    // nothing — the buffer is empty and there's no dropped-event sentinel.
    await flushPromises();
    vi.advanceTimersByTime(3000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requeues events when the fetch promise rejects", async () => {
    setupTracingEnabledEnv();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200 });
    // Silence the one-shot failure warning so test output stays clean.
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { initializeTracing } = await loadTracing();
    initializeTracing(BASE_URL);
    observerCallback!({ getEntries: () => [makeMarkEntry("retry-me")] });

    vi.advanceTimersByTime(3000);
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(3000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const replay = JSON.parse(fetchMock.mock.calls[1][1].body as string) as { events: Array<ChromeEvent> };
    expect(replay.events.map((event) => event.name)).toEqual(["retry-me"]);
  });

  it("requeues events when the fetch resolves with a non-2xx response", async () => {
    setupTracingEnabledEnv();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 });
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200 });
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { initializeTracing } = await loadTracing();
    initializeTracing(BASE_URL);
    observerCallback!({ getEntries: () => [makeMarkEntry("five-oh-three")] });

    vi.advanceTimersByTime(3000);
    await flushPromises();
    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const replay = JSON.parse(fetchMock.mock.calls[1][1].body as string) as { events: Array<ChromeEvent> };
    expect(replay.events.map((event) => event.name)).toEqual(["five-oh-three"]);
  });

  it("drops oldest events past the buffer cap and emits a tracing.dropped sentinel", async () => {
    setupTracingEnabledEnv();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { initializeTracing } = await loadTracing();
    initializeTracing(BASE_URL);
    // 20_001 entries pushes the buffer one past MAX_PENDING_EVENTS, which
    // should drop exactly one event and add a sentinel on the next flush.
    const overflowCount = 1;
    const totalEntries = 20_000 + overflowCount;
    const entries: Array<PerformanceEntry> = [];
    for (let i = 0; i < totalEntries; i += 1) {
      entries.push(makeMarkEntry(`m-${i}`));
    }
    observerCallback!({ getEntries: () => entries });

    vi.advanceTimersByTime(3000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = getLastFetchBody(fetchMock);
    expect(body.events).toHaveLength(20_000 + 1); // 20_000 marks + 1 sentinel
    const sentinel = body.events[body.events.length - 1];
    expect(sentinel.name).toBe("tracing.dropped");
    expect(sentinel.cat).toBe("tracing");
    expect(sentinel.args).toEqual({ count: overflowCount });
    // The dropped event is the oldest one ("m-0").
    expect(body.events[0]?.name).toBe("m-1");
  });

  it("uses navigator.sendBeacon (not fetch) on beforeunload", async () => {
    setupTracingEnabledEnv();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const sendBeacon = globalThis.navigator.sendBeacon as ReturnType<typeof vi.fn>;

    const { initializeTracing } = await loadTracing();
    initializeTracing(BASE_URL);
    observerCallback!({ getEntries: () => [makeMarkEntry("bye")] });

    window.dispatchEvent(new Event("beforeunload"));

    expect(sendBeacon).toHaveBeenCalledTimes(1);
    expect(sendBeacon.mock.calls[0][0]).toBe(TRACE_ENDPOINT);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("logs the first flush failure exactly once across repeated failures", async () => {
    setupTracingEnabledEnv();
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValue(new Error("offline"));
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    const { initializeTracing } = await loadTracing();
    initializeTracing(BASE_URL);
    observerCallback!({ getEntries: () => [makeMarkEntry("noisy")] });

    // Three failed flushes should yield exactly one console.warn.
    vi.advanceTimersByTime(3000);
    await flushPromises();
    vi.advanceTimersByTime(3000);
    await flushPromises();
    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0][0]).toContain("[tracing] flush failed");
  });
});
