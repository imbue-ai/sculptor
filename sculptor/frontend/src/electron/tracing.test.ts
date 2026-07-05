/** Tests for the Electron main-process tracing collector.
 *
 * The argv-parsing tests cover ``parseTraceToArg`` in isolation. The remaining
 * suites exercise the flush/retry/buffer-cap/lifecycle paths the same way the
 * renderer tests in ``common/perf/tracing.test.ts`` do: each test resets the module
 * registry and re-imports the module so the module-level mutable state
 * (``traceToPath``, ``pendingEvents``, ``backendUrlForFlush``, ``flushTimer``,
 * ``hasLoggedFlushFailure``) starts fresh.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as TracingModuleNamespace from "./tracing";
import { parseTraceToArg } from "./tracing";

type ChromeEvent = Record<string, unknown>;
type TracingModule = typeof TracingModuleNamespace;

const TRACE_PATH = "/tmp/electron-trace.json";
const BACKEND_URL = "https://backend.invalid";
const TRACE_ENDPOINT = `${BACKEND_URL}/api/v1/trace/batch`;

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

const getFetchBody = (
  fetchMock: ReturnType<typeof vi.fn>,
  index: number,
): { source: string; events: Array<ChromeEvent> } => {
  const call = fetchMock.mock.calls[index];
  return JSON.parse(call[1].body as string) as { source: string; events: Array<ChromeEvent> };
};

describe("parseTraceToArg", (): void => {
  it("returns null when no flag is present", (): void => {
    expect(parseTraceToArg(["electron", "--other-flag", "foo"])).toBeNull();
  });

  it("parses the unprefixed --trace-to=<path> form", (): void => {
    expect(parseTraceToArg(["electron", "--trace-to=/tmp/out.json"])).toBe("/tmp/out.json");
  });

  it("parses the --sculptor=--trace-to=<path> arg-forwarding form", (): void => {
    expect(parseTraceToArg(["electron", "--sculptor=--trace-to=/tmp/out.json"])).toBe("/tmp/out.json");
  });

  it("returns the first matching value if both are present", (): void => {
    expect(parseTraceToArg(["electron", "--sculptor=--trace-to=/a.json", "--trace-to=/b.json"])).toBe("/a.json");
  });
});

describe("traceMark", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("is a no-op when initializeElectronTracing was not called", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { traceMark, setBackendUrlForTracing } = await loadTracing();
    // Mark events while tracing is disabled — these must be dropped.
    traceMark("never-buffered");
    traceMark("also-never-buffered");
    // Setting the backend URL afterwards is also a no-op (no traceToPath),
    // so no flush timer is wired up and no fetch will ever happen.
    setBackendUrlForTracing(BACKEND_URL);
    vi.advanceTimersByTime(10_000);
    await flushPromises();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("pushes a Chrome JSON instant event with the right shape when enabled", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(BACKEND_URL);
    traceMark("hello");

    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = getFetchBody(fetchMock, 0);
    expect(body.events).toHaveLength(1);
    const event = body.events[0];
    expect(event.ph).toBe("i");
    expect(event.cat).toBe("mark");
    expect(event.name).toBe("hello");
    expect(event.s).toBe("t");
    expect(typeof event.ts).toBe("number");
    // ``ts`` is microseconds; performance.now() is positive.
    expect(event.ts as number).toBeGreaterThanOrEqual(0);
  });
});

describe("setBackendUrlForTracing", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("ignores subsequent calls (first-call-wins)", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });
    const firstUrl = "https://first.invalid";
    const secondUrl = "https://second.invalid";

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(firstUrl);
    setBackendUrlForTracing(secondUrl);
    traceMark("hello");

    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`${firstUrl}/api/v1/trace/batch`);
  });

  it("is a no-op when called with null", async () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(null);
    traceMark("nope");

    vi.advanceTimersByTime(10_000);
    await flushPromises();

    expect(setIntervalSpy).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("flush", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts the batch to /api/v1/trace/batch and clears pendingEvents on success", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(BACKEND_URL);
    traceMark("first");
    traceMark("second");
    traceMark("third");

    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(TRACE_ENDPOINT);
    expect(init.method).toBe("POST");
    const body = getFetchBody(fetchMock, 0);
    expect(body.source).toBe("electron_main");
    expect(body.events.map((event) => event.name)).toEqual(["first", "second", "third"]);

    // No new marks since the last flush; the next tick must not fire fetch.
    vi.advanceTimersByTime(3000);
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requeues events when the fetch promise rejects", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200 });
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(BACKEND_URL);
    traceMark("retry-me");

    vi.advanceTimersByTime(3000);
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const replay = getFetchBody(fetchMock, 1);
    expect(replay.events.map((event) => event.name)).toEqual(["retry-me"]);
  });

  it("requeues events when the fetch resolves with a non-2xx response", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 });
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200 });
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(BACKEND_URL);
    traceMark("five-oh-three");

    vi.advanceTimersByTime(3000);
    await flushPromises();
    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const replay = getFetchBody(fetchMock, 1);
    expect(replay.events.map((event) => event.name)).toEqual(["five-oh-three"]);
  });

  it("drops oldest events past the buffer cap and emits a tracing.dropped sentinel", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(BACKEND_URL);

    // 20_001 marks pushes the buffer one past MAX_PENDING_EVENTS, which
    // should drop exactly one event and add a sentinel on the next flush.
    const overflowCount = 1;
    const totalMarks = 20_000 + overflowCount;
    for (let i = 0; i < totalMarks; i += 1) {
      traceMark(`m-${i}`);
    }

    vi.advanceTimersByTime(3000);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = getFetchBody(fetchMock, 0);
    expect(body.events).toHaveLength(20_000 + 1); // 20_000 marks + 1 sentinel
    const sentinel = body.events[body.events.length - 1];
    expect(sentinel.name).toBe("tracing.dropped");
    expect(sentinel.cat).toBe("tracing");
    expect(sentinel.args).toEqual({ count: overflowCount });
    // The dropped event is the oldest one ("m-0").
    expect(body.events[0]?.name).toBe("m-1");
  });

  it("logs the first flush failure exactly once across repeated failures", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValue(new Error("offline"));
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(BACKEND_URL);
    traceMark("noisy");

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

describe("tracingTeardownGracePeriodMs", () => {
  it("returns the supplied default when tracing was never enabled", async () => {
    const { tracingTeardownGracePeriodMs } = await loadTracing();
    expect(tracingTeardownGracePeriodMs(32_000)).toBe(32_000);
    expect(tracingTeardownGracePeriodMs(15_000)).toBe(15_000);
  });

  it("returns the extended budget once initializeElectronTracing has run", async () => {
    const { initializeElectronTracing, tracingTeardownGracePeriodMs } = await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    // Any caller default is overridden; the actual number is policy, not a
    // contract the assertion needs to pin to a specific value, but it must
    // be much larger than the non-tracing default so the SIGKILL doesn't
    // fire mid-viztracer-flush.
    expect(tracingTeardownGracePeriodMs(32_000)).toBeGreaterThan(32_000);
    expect(tracingTeardownGracePeriodMs(15_000)).toBe(tracingTeardownGracePeriodMs(32_000));
  });
});

describe("flushTracingBeforeExit", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("drains pending events and clears the interval timer", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    const { initializeElectronTracing, setBackendUrlForTracing, traceMark, flushTracingBeforeExit } =
      await loadTracing();
    initializeElectronTracing(TRACE_PATH);
    setBackendUrlForTracing(BACKEND_URL);
    traceMark("bye-1");
    traceMark("bye-2");

    // Drive the flush directly instead of via the timer.
    await flushTracingBeforeExit();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = getFetchBody(fetchMock, 0);
    expect(body.source).toBe("electron_main");
    expect(body.events.map((event) => event.name)).toEqual(["bye-1", "bye-2"]);

    // Advancing past the next interval must not fire another fetch: the
    // interval handle was cleared by flushTracingBeforeExit.
    vi.advanceTimersByTime(10_000);
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
