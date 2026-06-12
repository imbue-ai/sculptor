import { act, renderHook } from "@testing-library/react";
import type { MouseEvent as ReactMouseEvent, MutableRefObject } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePillHoverDelay } from "../usePillHoverDelay.ts";

// Mirrors the constants in usePillHoverDelay.ts. Kept local so a future change
// to those values has to update the assertions here intentionally.
const OPEN_DELAY_MS = 600;
const CLOSE_DELAY_MS = 80;
const REOPEN_GRACE_PERIOD_MS = 300;
const SAFE_AREA_IDLE_MS = 1200;

// Fake popover element with a configurable bounding rect. Used to exercise the
// safe-area path, which short-circuits when the popover rect is zero-sized.
const makePopoverEl = (rect: { left: number; top: number; right: number; bottom: number }): HTMLElement => {
  const el = document.createElement("div");
  const domRect = new DOMRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top);
  el.getBoundingClientRect = (): DOMRect => domRect;
  return el;
};

// Build a fake React MouseEvent carrying only the fields the hook reads.
// `currentTarget` is the trigger/popover wrapper whose rect is folded into the
// safe-area hull.
const makeLeaveEvent = (
  clientX: number,
  clientY: number,
  triggerRect: { left: number; top: number; right: number; bottom: number },
): ReactMouseEvent => {
  const triggerEl = makePopoverEl(triggerRect);
  return { clientX, clientY, currentTarget: triggerEl } as unknown as ReactMouseEvent;
};

const dispatchMouseMove = (clientX: number, clientY: number): void => {
  document.dispatchEvent(new MouseEvent("mousemove", { clientX, clientY }));
};

type Setup = {
  setOpenPillId: ReturnType<typeof vi.fn>;
  isPinnedRef: MutableRefObject<boolean>;
  popoverElRef: MutableRefObject<HTMLElement | null>;
  /** Re-render the hook with a new openPillId. Simulates the parent's state update. */
  setOpen: (openPillId: string | null) => void;
  result: {
    current: ReturnType<typeof usePillHoverDelay>;
  };
};

const setup = (initialOpenPillId: string | null = null, popoverEl: HTMLElement | null = null): Setup => {
  const setOpenPillId = vi.fn();
  const isPinnedRef = { current: false } as MutableRefObject<boolean>;
  const popoverElRef = { current: popoverEl } as MutableRefObject<HTMLElement | null>;

  const { result, rerender } = renderHook(
    ({ openPillId }: { openPillId: string | null }) =>
      usePillHoverDelay({ openPillId, setOpenPillId, isPinnedRef, popoverElRef }),
    { initialProps: { openPillId: initialOpenPillId } },
  );

  return {
    setOpenPillId,
    isPinnedRef,
    popoverElRef,
    setOpen: (openPillId: string | null): void => rerender({ openPillId }),
    result,
  };
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("usePillHoverDelay", () => {
  describe("open delay", () => {
    it("opens the popover after OPEN_DELAY_MS when the user hovers a pill", () => {
      const { setOpenPillId, result } = setup(null);

      act(() => result.current.handlePillMouseEnter("pill-1"));

      // Just before the delay elapses — still closed.
      act(() => {
        vi.advanceTimersByTime(OPEN_DELAY_MS - 1);
      });
      expect(setOpenPillId).not.toHaveBeenCalled();

      // Crossing the delay opens the pill (unpinned).
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(setOpenPillId).toHaveBeenCalledWith("pill-1", false);
    });

    it("does not open if the user leaves the pill before the delay elapses", () => {
      const { setOpenPillId, result } = setup(null);

      act(() => result.current.handlePillMouseEnter("pill-1"));
      act(() => result.current.handlePillMouseLeave());

      act(() => {
        vi.advanceTimersByTime(OPEN_DELAY_MS + 100);
      });
      expect(setOpenPillId).not.toHaveBeenCalledWith("pill-1", false);
    });
  });

  describe("re-open grace period", () => {
    it("re-opens instantly when the user re-enters within the grace window after closing", () => {
      const { setOpenPillId, result, setOpen } = setup(null);

      // First hover & open.
      act(() => result.current.handlePillMouseEnter("pill-1"));
      act(() => {
        vi.advanceTimersByTime(OPEN_DELAY_MS);
      });
      expect(setOpenPillId).toHaveBeenLastCalledWith("pill-1", false);
      setOpen("pill-1");

      // Mouse leaves — close timer fires.
      act(() => result.current.handlePillMouseLeave());
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS);
      });
      expect(setOpenPillId).toHaveBeenLastCalledWith(null, false);
      setOpen(null);
      setOpenPillId.mockClear();

      // Re-enter inside the grace window — open should fire on the next tick.
      act(() => {
        vi.advanceTimersByTime(REOPEN_GRACE_PERIOD_MS - 50);
      });
      act(() => result.current.handlePillMouseEnter("pill-1"));
      // Delay is 0ms inside the grace window; flush the queued macrotask.
      act(() => {
        vi.advanceTimersByTime(0);
      });
      expect(setOpenPillId).toHaveBeenCalledWith("pill-1", false);
    });

    it("uses the full open delay when re-entering after the grace window expires", () => {
      const { setOpenPillId, result, setOpen } = setup(null);

      act(() => result.current.handlePillMouseEnter("pill-1"));
      act(() => {
        vi.advanceTimersByTime(OPEN_DELAY_MS);
      });
      setOpen("pill-1");

      act(() => result.current.handlePillMouseLeave());
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS);
      });
      setOpen(null);
      setOpenPillId.mockClear();

      // Wait past the grace window before re-entering.
      act(() => {
        vi.advanceTimersByTime(REOPEN_GRACE_PERIOD_MS + 50);
      });
      act(() => result.current.handlePillMouseEnter("pill-1"));

      // Within the open delay — still closed.
      act(() => {
        vi.advanceTimersByTime(OPEN_DELAY_MS - 1);
      });
      expect(setOpenPillId).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(setOpenPillId).toHaveBeenCalledWith("pill-1", false);
    });
  });

  describe("instant sibling switch", () => {
    it("switches to a sibling pill instantly while one popover is open and unpinned", () => {
      const { setOpenPillId, result, setOpen } = setup("pill-1");

      // Sliding from pill-1 to pill-2 — no waiting for the open delay.
      act(() => result.current.handlePillMouseEnter("pill-2"));
      expect(setOpenPillId).toHaveBeenCalledWith("pill-2", false);
      setOpen("pill-2");

      // No close timer should have fired in the meantime.
      setOpenPillId.mockClear();
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS + 50);
      });
      expect(setOpenPillId).not.toHaveBeenCalled();
    });
  });

  describe("pinned bypass", () => {
    it("ignores hover on a sibling while another pill is pinned", () => {
      const { setOpenPillId, isPinnedRef, result } = setup("pill-1");
      isPinnedRef.current = true;

      act(() => result.current.handlePillMouseEnter("pill-2"));
      // No open scheduled; no close fired.
      act(() => {
        vi.advanceTimersByTime(OPEN_DELAY_MS + CLOSE_DELAY_MS);
      });
      expect(setOpenPillId).not.toHaveBeenCalled();
    });

    it("does not auto-close a pinned popover when the user leaves the pill and popover", () => {
      const { setOpenPillId, isPinnedRef, result } = setup("pill-1");
      isPinnedRef.current = true;

      // Hover-enter to seed the pill-over flag, then leave.
      act(() => result.current.handlePillMouseEnter("pill-1"));
      act(() => result.current.handlePillMouseLeave());
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS + 50);
      });

      // setOpenPillId(null, ...) should never have been called.
      const calls = setOpenPillId.mock.calls.filter((c) => c[0] === null);
      expect(calls).toHaveLength(0);
    });
  });

  describe("close timer cancellation", () => {
    it("does not close when the mouse leaves the pill but enters the popover", () => {
      const { setOpenPillId, result } = setup("pill-1");

      act(() => result.current.handlePillMouseEnter("pill-1"));
      // Pill→popover handoff: leave the pill, then immediately enter the popover.
      act(() => result.current.handlePillMouseLeave());
      act(() => result.current.handlePopoverMouseEnter());

      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS + 50);
      });

      const closeCalls = setOpenPillId.mock.calls.filter((c) => c[0] === null);
      expect(closeCalls).toHaveLength(0);
    });

    it("closes after CLOSE_DELAY_MS once the mouse leaves both the pill and the popover", () => {
      const { setOpenPillId, result } = setup("pill-1");

      act(() => result.current.handlePopoverMouseEnter());
      act(() => result.current.handlePopoverMouseLeave());

      // Just before the delay fires — still open.
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS - 1);
      });
      expect(setOpenPillId).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(setOpenPillId).toHaveBeenCalledWith(null, false);
    });
  });

  describe("notifyPinnedToggle", () => {
    it("clears any pending open timer so a click overrides a hover-in-flight", () => {
      const { setOpenPillId, result } = setup(null);

      act(() => result.current.handlePillMouseEnter("pill-1"));
      // Click pins the pill before the hover-open delay fires.
      act(() => result.current.notifyPinnedToggle(true));

      act(() => {
        vi.advanceTimersByTime(OPEN_DELAY_MS + 50);
      });
      // The hover-open should not fire — the caller already opened it.
      expect(setOpenPillId).not.toHaveBeenCalled();
    });

    it("seeds the re-open grace window on close so a follow-up hover is instant", () => {
      const { setOpenPillId, result, setOpen } = setup("pill-1");

      // A click on the pinned pill: caller closes it via setOpenPillId(null) and
      // notifies the hook of the toggle.
      act(() => result.current.notifyPinnedToggle(false));
      setOpen(null);
      setOpenPillId.mockClear();

      // Following hover should bypass the open delay (instant via grace window).
      act(() => result.current.handlePillMouseEnter("pill-1"));
      act(() => {
        vi.advanceTimersByTime(0);
      });
      expect(setOpenPillId).toHaveBeenCalledWith("pill-1", false);
    });
  });

  describe("safe area (popoverElRef provided)", () => {
    // Trigger pill rect at (0,0)-(100,20); popover rect below it at (0,30)-(200,200).
    // Exit point (50, 22) sits between them, well inside the padded hull.
    const triggerRect = { left: 0, top: 0, right: 100, bottom: 20 };
    const popoverRect = { left: 0, top: 30, right: 200, bottom: 200 };

    it("holds the popover open while the cursor stays inside the safe polygon", () => {
      const popoverEl = makePopoverEl(popoverRect);
      const { setOpenPillId, result } = setup("pill-1", popoverEl);

      // Leave the pill heading toward the popover.
      act(() => result.current.handlePillMouseLeave(makeLeaveEvent(50, 22, triggerRect)));

      // The cursor moves through the safe corridor — no close should fire.
      act(() => dispatchMouseMove(50, 25));
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS + 50);
      });
      const closeCalls = setOpenPillId.mock.calls.filter((c) => c[0] === null);
      expect(closeCalls).toHaveLength(0);
    });

    it("closes after CLOSE_DELAY_MS once the cursor leaves the safe polygon", () => {
      const popoverEl = makePopoverEl(popoverRect);
      const { setOpenPillId, result } = setup("pill-1", popoverEl);

      act(() => result.current.handlePillMouseLeave(makeLeaveEvent(50, 22, triggerRect)));
      // Jump well away from the trigger and popover, beyond the 32px pad.
      act(() => dispatchMouseMove(500, 500));

      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS - 1);
      });
      expect(setOpenPillId).not.toHaveBeenCalledWith(null, false);

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(setOpenPillId).toHaveBeenCalledWith(null, false);
    });

    it("cancels a pending close when the cursor re-enters the safe polygon", () => {
      const popoverEl = makePopoverEl(popoverRect);
      const { setOpenPillId, result } = setup("pill-1", popoverEl);

      act(() => result.current.handlePillMouseLeave(makeLeaveEvent(50, 22, triggerRect)));
      // Step out (arms the pending close), then step back in before it fires.
      act(() => dispatchMouseMove(500, 500));
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS - 10);
      });
      act(() => dispatchMouseMove(50, 25));
      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS + 100);
      });

      const closeCalls = setOpenPillId.mock.calls.filter((c) => c[0] === null);
      expect(closeCalls).toHaveLength(0);
    });

    it("fires the idle close when the cursor stops moving inside the polygon", () => {
      const popoverEl = makePopoverEl(popoverRect);
      const { setOpenPillId, result } = setup("pill-1", popoverEl);

      act(() => result.current.handlePillMouseLeave(makeLeaveEvent(50, 22, triggerRect)));
      // Single in-polygon move resets the idle timer once, then no further motion.
      act(() => dispatchMouseMove(50, 25));

      act(() => {
        vi.advanceTimersByTime(SAFE_AREA_IDLE_MS - 1);
      });
      expect(setOpenPillId).not.toHaveBeenCalledWith(null, false);

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(setOpenPillId).toHaveBeenCalledWith(null, false);
    });

    it("falls back to the simple close path when no popover rect is available", () => {
      const { setOpenPillId, result } = setup("pill-1", null);

      act(() => result.current.handlePillMouseLeave(makeLeaveEvent(50, 22, triggerRect)));

      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS);
      });
      expect(setOpenPillId).toHaveBeenCalledWith(null, false);
    });

    it("holds the popover open when leaving the popover into the padded buffer (overshoot)", () => {
      // Symmetric to the pill→popover hold: leaving the popover edge toward a
      // header button shouldn't dismiss if the cursor lands within the
      // SAFE_AREA_PADDING_PX (32px) buffer.
      const popoverEl = makePopoverEl(popoverRect);
      const { setOpenPillId, result } = setup("pill-1", popoverEl);

      // Exit just past the popover's top-right corner — within the padded hull.
      act(() => result.current.handlePopoverMouseLeave(makeLeaveEvent(205, 28, popoverRect)));
      act(() => dispatchMouseMove(210, 26));

      act(() => {
        vi.advanceTimersByTime(CLOSE_DELAY_MS + 50);
      });
      const closeCalls = setOpenPillId.mock.calls.filter((c) => c[0] === null);
      expect(closeCalls).toHaveLength(0);
    });
  });
});
