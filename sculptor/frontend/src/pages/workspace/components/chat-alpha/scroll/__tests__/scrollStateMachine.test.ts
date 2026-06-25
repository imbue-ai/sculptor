import { describe, expect, it, vi } from "vitest";

import {
  createScrollStateMachine,
  isScrollSettled,
  projectAtBottom,
  SCROLL_PHASE_ATTR,
  SCROLL_SETTLED_ATTR,
} from "../scrollStateMachine.ts";

describe("createScrollStateMachine", () => {
  it("starts userControlled / stable / not suppressed and settled", () => {
    const m = createScrollStateMachine();
    expect(m.getState()).toEqual({
      authority: { kind: "userControlled" },
      layout: { kind: "stable" },
      isSuppressed: false,
      geometryAtBottom: true,
    });
    expect(isScrollSettled(m.getState())).toBe(true);
  });

  it("dispatches authority events and notifies subscribers", () => {
    const m = createScrollStateMachine();
    const listener = vi.fn();
    m.subscribe(listener);

    m.dispatch({ kind: "taskSwitched", taskId: "t1" });

    expect(m.getState().authority).toEqual({ kind: "restoring", taskId: "t1" });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("does not notify on a no-op transition", () => {
    const m = createScrollStateMachine();
    const listener = vi.fn();
    m.subscribe(listener);

    // userScrolled while already userControlled is a no-op.
    m.dispatch({ kind: "userScrolled" });

    expect(listener).not.toHaveBeenCalled();
  });

  it("reflects phase and settled onto the attached element", () => {
    const m = createScrollStateMachine();
    const el = document.createElement("div");
    m.attach(el);

    // attach reflects the initial state immediately.
    expect(el.getAttribute(SCROLL_PHASE_ATTR)).toBe("userControlled");
    expect(el.getAttribute(SCROLL_SETTLED_ATTR)).toBe("true");

    m.dispatch({ kind: "taskSwitched", taskId: "t1" });
    expect(el.getAttribute(SCROLL_PHASE_ATTR)).toBe("restoring");
    expect(el.getAttribute(SCROLL_SETTLED_ATTR)).toBe("false");

    m.dispatch({ kind: "restoreSettled" });
    expect(el.getAttribute(SCROLL_PHASE_ATTR)).toBe("userControlled");
    expect(el.getAttribute(SCROLL_SETTLED_ATTR)).toBe("true");
  });

  it("treats following as settled but anchoringTurn/restoring/navigating as busy", () => {
    expect(
      isScrollSettled({
        authority: { kind: "following" },
        layout: { kind: "stable" },
        isSuppressed: false,
        geometryAtBottom: true,
      }),
    ).toBe(true);
    expect(
      isScrollSettled({
        authority: { kind: "anchoringTurn", anchorIndex: 1 },
        layout: { kind: "stable" },
        isSuppressed: false,
        geometryAtBottom: false,
      }),
    ).toBe(false);
    expect(
      isScrollSettled({
        authority: { kind: "navigating", promptIndex: 0 },
        layout: { kind: "stable" },
        isSuppressed: false,
        geometryAtBottom: false,
      }),
    ).toBe(false);
  });

  it("is not settled while layout is measuring even if authority is quiescent", () => {
    const m = createScrollStateMachine();
    const el = document.createElement("div");
    m.attach(el);

    m.dispatchLayout({ kind: "invalidated", taskId: "t1" });
    expect(isScrollSettled(m.getState())).toBe(false);
    expect(el.getAttribute(SCROLL_SETTLED_ATTR)).toBe("false");

    m.dispatchLayout({ kind: "converged" });
    expect(el.getAttribute(SCROLL_SETTLED_ATTR)).toBe("true");
  });

  describe("projectAtBottom", () => {
    it("is true while following regardless of the sampled geometry", () => {
      expect(
        projectAtBottom({
          authority: { kind: "following" },
          layout: { kind: "stable" },
          isSuppressed: false,
          geometryAtBottom: false,
        }),
      ).toBe(true);
    });

    it("is false while anchoring a turn regardless of the sampled geometry", () => {
      expect(
        projectAtBottom({
          authority: { kind: "anchoringTurn", anchorIndex: 3 },
          layout: { kind: "stable" },
          isSuppressed: false,
          geometryAtBottom: true,
        }),
      ).toBe(false);
    });

    it("defers to the sampled geometry in every other phase", () => {
      for (const authority of [
        { kind: "userControlled" } as const,
        { kind: "restoring", taskId: "t" } as const,
        { kind: "navigating", promptIndex: 0 } as const,
      ]) {
        expect(
          projectAtBottom({ authority, layout: { kind: "stable" }, isSuppressed: false, geometryAtBottom: true }),
        ).toBe(true);
        expect(
          projectAtBottom({ authority, layout: { kind: "stable" }, isSuppressed: false, geometryAtBottom: false }),
        ).toBe(false);
      }
    });
  });

  describe("setGeometryAtBottom", () => {
    it("notifies subscribers when the sampled geometry changes", () => {
      const m = createScrollStateMachine();
      const listener = vi.fn();
      m.subscribe(listener);

      m.setGeometryAtBottom(false);
      expect(m.getState().geometryAtBottom).toBe(false);
      expect(listener).toHaveBeenCalledTimes(1);
    });

    it("does not notify when the sampled geometry is unchanged", () => {
      const m = createScrollStateMachine();
      const listener = vi.fn();
      m.subscribe(listener);

      // Starts true — re-asserting true is a no-op (matters for the per-frame
      // resize sampling during `following`, which must not churn re-renders).
      m.setGeometryAtBottom(true);
      expect(listener).not.toHaveBeenCalled();
    });
  });

  describe("search suppression (top-level guard)", () => {
    it("drops auto-scroll initiation events while suppressed", () => {
      const m = createScrollStateMachine();
      m.setSuppressed(true);

      m.dispatch({ kind: "newUserTurn", index: 2 });
      m.dispatch({ kind: "reachedBottom" });

      expect(m.getState().authority).toEqual({ kind: "userControlled" });
    });

    it("still applies global and completion events while suppressed", () => {
      const m = createScrollStateMachine();
      m.setSuppressed(true);

      m.dispatch({ kind: "taskSwitched", taskId: "t1" });
      expect(m.getState().authority).toEqual({ kind: "restoring", taskId: "t1" });

      m.dispatch({ kind: "userScrolled" });
      expect(m.getState().authority).toEqual({ kind: "userControlled" });
    });

    it("resumes auto-scroll once suppression clears", () => {
      const m = createScrollStateMachine();
      m.setSuppressed(true);
      m.dispatch({ kind: "reachedBottom" });
      expect(m.getState().authority).toEqual({ kind: "userControlled" });

      m.setSuppressed(false);
      m.dispatch({ kind: "reachedBottom" });
      expect(m.getState().authority).toEqual({ kind: "following" });
    });
  });

  it("stops notifying after unsubscribe", () => {
    const m = createScrollStateMachine();
    const listener = vi.fn();
    const unsubscribe = m.subscribe(listener);

    m.dispatch({ kind: "taskSwitched", taskId: "t1" });
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    m.dispatch({ kind: "userScrolled" });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("tolerates detaching the element", () => {
    const m = createScrollStateMachine();
    const el = document.createElement("div");
    m.attach(el);
    m.attach(null);
    expect(() => m.dispatch({ kind: "taskSwitched", taskId: "t1" })).not.toThrow();
  });
});
