import { act, renderHook } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToolNavigationProvider, useToolNavigation } from "../ToolNavigationContext.tsx";

const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
  <ToolNavigationProvider>{children}</ToolNavigationProvider>
);

const useNav = (): NonNullable<ReturnType<typeof useToolNavigation>> => {
  const nav = useToolNavigation();
  if (!nav) throw new Error("ToolNavigationProvider missing");
  return nav;
};

/**
 * Build a fake button element whose getBoundingClientRect returns the supplied
 * left/width. Used to drive vertical (up/down) navigation, which picks the
 * target row's item with the closest horizontal center.
 */
const makeFakeItemEl = (left: number, width = 40): HTMLButtonElement => {
  const el = document.createElement("button");
  el.getBoundingClientRect = (): DOMRect => ({
    left,
    width,
    top: 0,
    height: 24,
    right: left + width,
    bottom: 24,
    x: left,
    y: 0,
    toJSON: () => ({}),
  });
  // Avoid scrollIntoView/focus throwing in jsdom (they exist but as no-ops).
  el.scrollIntoView = vi.fn();
  el.focus = vi.fn();
  return el;
};

describe("ToolNavigationContext", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("setOpenItemId", () => {
    it("treats hover opens (pinned=false) as unpinned", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => result.current.setOpenItemId("a", false));

      expect(result.current.openItemId).toBe("a");
      expect(result.current.isPinnedRef.current).toBe(false);
    });

    it("treats default opens as pinned (the click/keyboard path)", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => result.current.setOpenItemId("a"));

      expect(result.current.openItemId).toBe("a");
      expect(result.current.isPinnedRef.current).toBe(true);
    });

    it("clears pinned when closing (id=null)", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => result.current.setOpenItemId("a"));
      act(() => result.current.setOpenItemId(null));

      expect(result.current.openItemId).toBe(null);
      expect(result.current.isPinnedRef.current).toBe(false);
    });
  });

  describe("registerRow / unregisterRow", () => {
    it("registers a row's items so prev/next walks through them", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        result.current.registerRow(0, ["a", "b", "c"]);
        result.current.setItemRef("a", makeFakeItemEl(0));
        result.current.setItemRef("b", makeFakeItemEl(50));
        result.current.setItemRef("c", makeFakeItemEl(100));
        result.current.setOpenItemId("a");
      });

      act(() => result.current.navigate("next"));
      expect(result.current.openItemId).toBe("b");

      act(() => result.current.navigate("next"));
      expect(result.current.openItemId).toBe("c");

      // Clamped at the end.
      act(() => result.current.navigate("next"));
      expect(result.current.openItemId).toBe("c");

      act(() => result.current.navigate("prev"));
      expect(result.current.openItemId).toBe("b");
    });

    it("removes the row from navigation when unregistered", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        result.current.registerRow(0, ["a", "b"]);
        result.current.setItemRef("a", makeFakeItemEl(0));
        result.current.setItemRef("b", makeFakeItemEl(50));
        result.current.setOpenItemId("a");
        result.current.unregisterRow(0);
      });

      // Empty registry — navigate() should be a no-op.
      act(() => result.current.navigate("next"));
      expect(result.current.openItemId).toBe("a");
    });
  });

  describe("navigate prev/next", () => {
    it("walks across multiple rows in order of rowIndex", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        result.current.registerRow(0, ["a", "b"]);
        result.current.registerRow(1, ["c", "d"]);
        result.current.setItemRef("a", makeFakeItemEl(0));
        result.current.setItemRef("b", makeFakeItemEl(50));
        result.current.setItemRef("c", makeFakeItemEl(0));
        result.current.setItemRef("d", makeFakeItemEl(50));
        result.current.setOpenItemId("b");
      });

      // b → c crosses the row boundary.
      act(() => result.current.navigate("next"));
      expect(result.current.openItemId).toBe("c");

      // and back.
      act(() => result.current.navigate("prev"));
      expect(result.current.openItemId).toBe("b");
    });

    it("uses fromId when no item is open", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        result.current.registerRow(0, ["a", "b", "c"]);
        result.current.setItemRef("a", makeFakeItemEl(0));
        result.current.setItemRef("b", makeFakeItemEl(50));
        result.current.setItemRef("c", makeFakeItemEl(100));
      });

      // Nothing open; explicit fromId anchors navigation.
      act(() => result.current.navigate("next", "a"));
      expect(result.current.openItemId).toBe("b");
    });

    it("does nothing when nothing is open and no fromId is provided", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        result.current.registerRow(0, ["a", "b"]);
      });

      act(() => result.current.navigate("next"));
      expect(result.current.openItemId).toBe(null);
    });
  });

  describe("navigate up/down", () => {
    it("up jumps to the adjacent row, picking the item closest to the source's horizontal center", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        // Top row: items at x=0, 100, 200.
        result.current.registerRow(0, ["t1", "t2", "t3"]);
        result.current.setItemRef("t1", makeFakeItemEl(0));
        result.current.setItemRef("t2", makeFakeItemEl(100));
        result.current.setItemRef("t3", makeFakeItemEl(200));

        // Bottom row: items at x=20, 110.
        result.current.registerRow(1, ["b1", "b2"]);
        result.current.setItemRef("b1", makeFakeItemEl(20));
        result.current.setItemRef("b2", makeFakeItemEl(110));

        // Open the bottom-row item at x=110 (center=130).
        result.current.setOpenItemId("b2");
      });

      act(() => result.current.navigate("up"));
      // Top-row centers: t1=20, t2=120, t3=220. Closest to 130 is t2.
      expect(result.current.openItemId).toBe("t2");
    });

    it("down jumps from the top row to the next row", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        result.current.registerRow(0, ["t1", "t2"]);
        result.current.setItemRef("t1", makeFakeItemEl(0));
        result.current.setItemRef("t2", makeFakeItemEl(50));

        result.current.registerRow(1, ["b1", "b2"]);
        result.current.setItemRef("b1", makeFakeItemEl(0));
        result.current.setItemRef("b2", makeFakeItemEl(50));

        result.current.setOpenItemId("t1");
      });

      act(() => result.current.navigate("down"));
      expect(result.current.openItemId).toBe("b1");
    });

    it("is a no-op past the first or last row", () => {
      const { result } = renderHook(() => useNav(), { wrapper });

      act(() => {
        result.current.registerRow(0, ["a"]);
        result.current.setItemRef("a", makeFakeItemEl(0));
        result.current.setOpenItemId("a");
      });

      act(() => result.current.navigate("up"));
      expect(result.current.openItemId).toBe("a");
      act(() => result.current.navigate("down"));
      expect(result.current.openItemId).toBe("a");
    });
  });

  describe("setItemRef", () => {
    it("removes the entry when called with null", () => {
      const { result } = renderHook(() => useNav(), { wrapper });
      const el = makeFakeItemEl(0);

      act(() => {
        result.current.registerRow(0, ["a", "b"]);
        result.current.setItemRef("a", el);
        result.current.setItemRef("b", makeFakeItemEl(50));
        result.current.setItemRef("a", null);
      });

      // Vertical nav from b can't pivot off "a" (no rect), but prev/next still works.
      act(() => result.current.setOpenItemId("b"));
      act(() => result.current.navigate("prev"));
      expect(result.current.openItemId).toBe("a");
    });
  });
});
