import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTimedLatch } from "./useTimedLatch.ts";

describe("useTimedLatch", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("without a leading delay (default)", () => {
    it("turns on immediately when active goes true", () => {
      const { result, rerender } = renderHook(({ active }) => useTimedLatch(active, 500), {
        initialProps: { active: false },
      });
      expect(result.current).toBe(false);

      act(() => {
        rerender({ active: true });
      });
      expect(result.current).toBe(true);
    });

    it("holds for at least minHoldMs after active goes false", () => {
      const { result, rerender } = renderHook(({ active }) => useTimedLatch(active, 500), {
        initialProps: { active: false },
      });

      act(() => {
        rerender({ active: true });
      });
      // A fetch that completes in under a frame: flip straight back to false.
      act(() => {
        rerender({ active: false });
      });
      // Still latched — the min-hold keeps it visible.
      expect(result.current).toBe(true);

      act(() => {
        vi.advanceTimersByTime(499);
      });
      expect(result.current).toBe(true);

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(result.current).toBe(false);
    });

    it("releases promptly once an active period has already exceeded minHoldMs", () => {
      const { result, rerender } = renderHook(({ active }) => useTimedLatch(active, 500), {
        initialProps: { active: false },
      });

      act(() => {
        rerender({ active: true });
      });
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      act(() => {
        rerender({ active: false });
      });
      // The latch was already held longer than the min-hold, so there is no
      // remaining time to wait — it should clear on the next timer flush.
      act(() => {
        vi.advanceTimersByTime(0);
      });
      expect(result.current).toBe(false);
    });
  });

  describe("with a leading delay", () => {
    it("never shows for a fetch that finishes inside the delay window", () => {
      const { result, rerender } = renderHook(({ active }) => useTimedLatch(active, 500, 120), {
        initialProps: { active: false },
      });

      act(() => {
        rerender({ active: true });
      });
      // Not yet — we are inside the leading-delay window.
      expect(result.current).toBe(false);

      act(() => {
        vi.advanceTimersByTime(100);
      });
      expect(result.current).toBe(false);

      // Fetch completes at 100ms, before the 120ms delay elapses.
      act(() => {
        rerender({ active: false });
      });
      expect(result.current).toBe(false);

      // Confirm the (cancelled) delay timer never fires the latch on.
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(result.current).toBe(false);
    });

    it("shows after the delay elapses and then holds for minHoldMs", () => {
      const { result, rerender } = renderHook(({ active }) => useTimedLatch(active, 500, 120), {
        initialProps: { active: false },
      });

      act(() => {
        rerender({ active: true });
      });
      act(() => {
        vi.advanceTimersByTime(120);
      });
      // Delay elapsed: the bar is now visible.
      expect(result.current).toBe(true);

      // Fetch continues, then ends.
      act(() => {
        vi.advanceTimersByTime(180);
      });
      act(() => {
        rerender({ active: false });
      });
      // Held by the trailing min-hold (measured from when it turned on).
      expect(result.current).toBe(true);

      act(() => {
        vi.advanceTimersByTime(100);
      });
      expect(result.current).toBe(true);

      act(() => {
        vi.advanceTimersByTime(400);
      });
      expect(result.current).toBe(false);
    });

    it("requires a continuous active window — a mid-delay drop restarts the timer", () => {
      const { result, rerender } = renderHook(({ active }) => useTimedLatch(active, 500, 120), {
        initialProps: { active: false },
      });

      // First active stretch: 80ms (below the delay).
      act(() => {
        rerender({ active: true });
      });
      act(() => {
        vi.advanceTimersByTime(80);
      });
      act(() => {
        rerender({ active: false });
      });
      expect(result.current).toBe(false);

      // Second active stretch starts fresh; 80ms more is still below the delay,
      // so the two partial windows must not add up to cross it.
      act(() => {
        rerender({ active: true });
      });
      act(() => {
        vi.advanceTimersByTime(80);
      });
      expect(result.current).toBe(false);

      // A full continuous window finally crosses the delay.
      act(() => {
        vi.advanceTimersByTime(40);
      });
      expect(result.current).toBe(true);
    });
  });
});
