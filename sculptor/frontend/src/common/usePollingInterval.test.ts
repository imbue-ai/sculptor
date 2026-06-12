import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePollingInterval } from "./usePollingInterval.ts";

describe("usePollingInterval", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not poll until startPolling is called", () => {
    const pollFn = vi.fn().mockResolvedValue(undefined);
    renderHook(() => usePollingInterval());

    vi.advanceTimersByTime(10_000);
    expect(pollFn).not.toHaveBeenCalled();
  });

  it("polls at the default interval after startPolling is called", async () => {
    const pollFn = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => usePollingInterval());

    act(() => {
      result.current.startPolling(pollFn);
    });

    expect(pollFn).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(3000);
    expect(pollFn).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(3000);
    expect(pollFn).toHaveBeenCalledTimes(2);
  });

  it("polls at a custom interval", async () => {
    const pollFn = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => usePollingInterval({ intervalMs: 1000 }));

    act(() => {
      result.current.startPolling(pollFn);
    });

    await vi.advanceTimersByTimeAsync(1000);
    expect(pollFn).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1000);
    expect(pollFn).toHaveBeenCalledTimes(2);
  });

  it("stops polling when stopPolling is called", async () => {
    const pollFn = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => usePollingInterval());

    act(() => {
      result.current.startPolling(pollFn);
    });

    await vi.advanceTimersByTimeAsync(3000);
    expect(pollFn).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.stopPolling();
    });

    await vi.advanceTimersByTimeAsync(9000);
    expect(pollFn).toHaveBeenCalledTimes(1);
  });

  it("automatically stops after the safety timeout", async () => {
    const pollFn = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => usePollingInterval({ intervalMs: 1000, timeoutMs: 5000 }));

    act(() => {
      result.current.startPolling(pollFn);
    });

    await vi.advanceTimersByTimeAsync(4000);
    expect(pollFn).toHaveBeenCalledTimes(4);

    // At 5000ms both the interval and the timeout fire — the 5th tick runs
    // before the timeout clears the interval. After that, no more ticks.
    await vi.advanceTimersByTimeAsync(3000);
    expect(pollFn).toHaveBeenCalledTimes(5);
  });

  it("cleans up on unmount", async () => {
    const pollFn = vi.fn().mockResolvedValue(undefined);
    const { result, unmount } = renderHook(() => usePollingInterval());

    act(() => {
      result.current.startPolling(pollFn);
    });

    await vi.advanceTimersByTimeAsync(3000);
    expect(pollFn).toHaveBeenCalledTimes(1);

    unmount();

    await vi.advanceTimersByTimeAsync(9000);
    expect(pollFn).toHaveBeenCalledTimes(1);
  });

  it("skips a tick when the previous poll is still in-flight", async () => {
    let resolveFirst: () => void;
    const firstCallPromise = new Promise<void>((resolve) => {
      resolveFirst = resolve;
    });

    const pollFn = vi
      .fn()
      .mockImplementationOnce(() => firstCallPromise)
      .mockResolvedValue(undefined);
    const { result } = renderHook(() => usePollingInterval({ intervalMs: 1000 }));

    act(() => {
      result.current.startPolling(pollFn);
    });

    // First tick fires at 1000ms — starts the slow request
    vi.advanceTimersByTime(1000);
    expect(pollFn).toHaveBeenCalledTimes(1);

    // Second tick fires at 2000ms — should be skipped (first still in-flight)
    vi.advanceTimersByTime(1000);
    expect(pollFn).toHaveBeenCalledTimes(1);

    // Resolve the first request
    resolveFirst!();
    await act(async () => {
      await firstCallPromise;
    });

    // Third tick fires at 3000ms — should proceed (first completed)
    vi.advanceTimersByTime(1000);
    expect(pollFn).toHaveBeenCalledTimes(2);
  });

  it("resets in-flight guard when poll function rejects", async () => {
    const error = new Error("poll failed");
    const pollFn = vi.fn().mockRejectedValueOnce(error).mockResolvedValue(undefined);
    const { result } = renderHook(() => usePollingInterval({ intervalMs: 1000 }));

    act(() => {
      result.current.startPolling(pollFn);
    });

    // First tick — rejects
    vi.advanceTimersByTime(1000);
    await act(async () => {
      // Flush the rejected promise
      await vi.advanceTimersByTimeAsync(0);
    });

    // Second tick — should proceed because the guard was reset via .finally()
    vi.advanceTimersByTime(1000);
    expect(pollFn).toHaveBeenCalledTimes(2);
  });

  it("clears previous polling when startPolling is called again", async () => {
    const firstPollFn = vi.fn().mockResolvedValue(undefined);
    const secondPollFn = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => usePollingInterval());

    act(() => {
      result.current.startPolling(firstPollFn);
    });

    await vi.advanceTimersByTimeAsync(3000);
    expect(firstPollFn).toHaveBeenCalledTimes(1);

    // Start new polling — should replace the previous one
    act(() => {
      result.current.startPolling(secondPollFn);
    });

    await vi.advanceTimersByTimeAsync(3000);
    expect(firstPollFn).toHaveBeenCalledTimes(1);
    expect(secondPollFn).toHaveBeenCalledTimes(1);
  });
});
