import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useInterval } from "./useInterval.ts";

describe("useInterval", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls the callback at the specified interval", () => {
    const callback = vi.fn();
    renderHook(() => useInterval(callback, 1000));

    expect(callback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(2);
  });

  it("does not call the callback before the interval elapses", () => {
    const callback = vi.fn();
    renderHook(() => useInterval(callback, 5000));

    vi.advanceTimersByTime(4999);
    expect(callback).not.toHaveBeenCalled();
  });

  it("cleans up the interval on unmount", () => {
    const callback = vi.fn();
    const { unmount } = renderHook(() => useInterval(callback, 1000));

    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(1);

    unmount();

    vi.advanceTimersByTime(5000);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("uses the latest callback without restarting the interval", () => {
    const firstCallback = vi.fn();
    const secondCallback = vi.fn();

    const { rerender } = renderHook(({ cb }) => useInterval(cb, 1000), {
      initialProps: { cb: firstCallback },
    });

    vi.advanceTimersByTime(500);
    rerender({ cb: secondCallback });

    // The remaining 500ms should fire the new callback, not the old one
    vi.advanceTimersByTime(500);
    expect(firstCallback).not.toHaveBeenCalled();
    expect(secondCallback).toHaveBeenCalledTimes(1);
  });

  it("restarts the interval when intervalMs changes", () => {
    const callback = vi.fn();

    const { rerender } = renderHook(({ ms }) => useInterval(callback, ms), {
      initialProps: { ms: 1000 },
    });

    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(1);

    // Change interval to 500ms — timer restarts
    rerender({ ms: 500 });

    vi.advanceTimersByTime(500);
    expect(callback).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(500);
    expect(callback).toHaveBeenCalledTimes(3);
  });
});
