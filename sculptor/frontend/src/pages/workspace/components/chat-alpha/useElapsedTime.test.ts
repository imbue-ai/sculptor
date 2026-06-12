import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useElapsedTime } from "./useElapsedTime.ts";

let testKeyCounter = 0;
/** Generate a unique persist key per test to avoid cross-test interference. */
const nextKey = (): string => `test-${++testKeyCounter}`;

// Mock requestAnimationFrame/cancelAnimationFrame to be timer-based
// so we can control ticking with vi.advanceTimersByTime
let rafCallbacks: Map<number, FrameRequestCallback>;
let nextRafId: number;

beforeEach(() => {
  vi.useFakeTimers();
  rafCallbacks = new Map();
  nextRafId = 1;

  vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation((cb: FrameRequestCallback): number => {
    const id = nextRafId++;
    rafCallbacks.set(id, cb);
    // Schedule the callback to run after a short delay (simulating ~60fps frame)
    setTimeout(() => {
      if (rafCallbacks.has(id)) {
        rafCallbacks.delete(id);
        cb(performance.now());
      }
    }, 16);
    return id;
  });

  vi.spyOn(globalThis, "cancelAnimationFrame").mockImplementation((id: number): void => {
    rafCallbacks.delete(id);
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useElapsedTime", () => {
  describe("basic timing", () => {
    it("starts at 0.0s when visible", () => {
      const key = nextKey();
      const { result } = renderHook(() => useElapsedTime(true, true, key));
      expect(result.current.elapsed).toBe("0.0s");
    });

    it("shows 0.0s when not visible", () => {
      const key = nextKey();
      const { result } = renderHook(() => useElapsedTime(false, false, key));
      expect(result.current.elapsed).toBe("0.0s");
    });

    it("advances time while ticking", () => {
      const key = nextKey();
      const { result } = renderHook(() => useElapsedTime(true, true, key));

      // Advance 1 second
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      // Should show approximately 1.0s (may vary slightly due to rAF timing)
      const seconds = parseFloat(result.current.elapsed);
      expect(seconds).toBeGreaterThanOrEqual(0.9);
      expect(seconds).toBeLessThanOrEqual(1.5);
    });

    it("advances time while ticking (both visible and ticking)", () => {
      const key = nextKey();
      const { result } = renderHook(() => useElapsedTime(true, true, key));

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const seconds = parseFloat(result.current.elapsed);
      expect(seconds).toBeGreaterThanOrEqual(1.5);
    });
  });

  describe("visibility transitions", () => {
    it("resets to 0.0s when becoming invisible", () => {
      const key = nextKey();
      const { result, rerender } = renderHook(({ visible }) => useElapsedTime(visible, visible, key), {
        initialProps: { visible: true },
      });

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      // Should have some elapsed time
      expect(parseFloat(result.current.elapsed)).toBeGreaterThan(0);

      // Go invisible
      rerender({ visible: false });
      expect(result.current.elapsed).toBe("0.0s");
    });

    it("resets and starts fresh when becoming visible again", () => {
      const key = nextKey();
      const { result, rerender } = renderHook(({ visible }) => useElapsedTime(visible, visible, key), {
        initialProps: { visible: true },
      });

      act(() => {
        vi.advanceTimersByTime(5000);
      });

      // Go invisible
      rerender({ visible: false });
      expect(result.current.elapsed).toBe("0.0s");

      // Go visible again — should restart from 0
      rerender({ visible: true });
      expect(result.current.elapsed).toBe("0.0s");

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      // Should be around 1s, not 6s
      const seconds = parseFloat(result.current.elapsed);
      expect(seconds).toBeLessThan(2);
    });
  });

  describe("freeze behavior (isTicking=false)", () => {
    it("freezes the timer when isTicking becomes false", () => {
      const key = nextKey();
      const { result, rerender } = renderHook(
        ({ visible, ticking }: { visible: boolean; ticking: boolean }) => useElapsedTime(visible, ticking, key),
        { initialProps: { visible: true, ticking: true } },
      );

      // Let it tick for 2 seconds
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const frozenValue = result.current.elapsed;
      const frozenSeconds = parseFloat(frozenValue);
      expect(frozenSeconds).toBeGreaterThan(0);

      // Freeze
      rerender({ visible: true, ticking: false });

      // Advance more time — should stay frozen
      act(() => {
        vi.advanceTimersByTime(3000);
      });

      expect(result.current.elapsed).toBe(frozenValue);
    });

    it("does not tick when starting with isTicking=false", () => {
      const key = nextKey();
      const { result } = renderHook(() => useElapsedTime(true, false, key));

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      expect(result.current.elapsed).toBe("0.0s");
    });

    it("resumes from frozen value when isTicking becomes true again", () => {
      const key = nextKey();
      const { result, rerender } = renderHook(
        ({ visible, ticking }: { visible: boolean; ticking: boolean }) => useElapsedTime(visible, ticking, key),
        { initialProps: { visible: true, ticking: true } },
      );

      // Tick for 2 seconds
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const frozenSeconds = parseFloat(result.current.elapsed);

      // Freeze
      rerender({ visible: true, ticking: false });

      // Wait while frozen
      act(() => {
        vi.advanceTimersByTime(5000);
      });

      // Resume
      rerender({ visible: true, ticking: true });

      // Tick 1 more second
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      // Should be approximately frozenSeconds + 1, NOT frozenSeconds + 6
      const resumed = parseFloat(result.current.elapsed);
      expect(resumed).toBeGreaterThanOrEqual(frozenSeconds + 0.5);
      expect(resumed).toBeLessThan(frozenSeconds + 2);
    });
  });

  describe("persistKey change (workspace tab switch)", () => {
    it("continues ticking after persistKey changes while visible and ticking", () => {
      const keyA = nextKey();
      const keyB = nextKey();

      // Start timer for workspace A
      const { result, rerender } = renderHook(
        ({ visible, ticking, key }: { visible: boolean; ticking: boolean; key: string }) =>
          useElapsedTime(visible, ticking, key),
        { initialProps: { visible: true, ticking: true, key: keyA } },
      );

      // Let workspace A tick for 2 seconds
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(parseFloat(result.current.elapsed)).toBeGreaterThan(0);

      // Switch to workspace B (persistKey changes, but visible and ticking stay true)
      rerender({ visible: true, ticking: true, key: keyB });

      // Advance 1 second — timer should continue ticking, not get stuck
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      const seconds = parseFloat(result.current.elapsed);
      expect(seconds).toBeGreaterThanOrEqual(0.5);
    });
  });

  describe("output format", () => {
    it("formats as N.Ns", () => {
      const key = nextKey();
      const { result } = renderHook(() => useElapsedTime(true, true, key));

      act(() => {
        vi.advanceTimersByTime(3500);
      });

      // Should match the pattern N.Ns
      expect(result.current.elapsed).toMatch(/^\d+\.\d{1}s$/);
    });
  });
});
