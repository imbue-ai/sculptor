import { describe, expect, it, vi } from "vitest";

import type { ScrollMachineState } from "../scrollStateMachine.ts";
import {
  createScrollStateMachine,
  isScrollSettled,
  projectAtBottom,
  projectReflow,
  SCROLL_PHASE_ATTR,
  SCROLL_SETTLED_ATTR,
} from "../scrollStateMachine.ts";

const stateWith = (over: Partial<ScrollMachineState>): ScrollMachineState => ({
  authority: { kind: "userControlled" },
  layout: { kind: "stable" },
  isSuppressed: false,
  geometryAtBottom: true,
  readingAnchor: null,
  ...over,
});

describe("createScrollStateMachine", () => {
  it("starts userControlled / stable / not suppressed and settled", () => {
    const m = createScrollStateMachine();
    expect(m.getState()).toEqual({
      authority: { kind: "userControlled" },
      layout: { kind: "stable" },
      isSuppressed: false,
      geometryAtBottom: true,
      readingAnchor: null,
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
        readingAnchor: null,
      }),
    ).toBe(true);
    expect(
      isScrollSettled({
        authority: { kind: "anchoringTurn", anchorIndex: 1 },
        layout: { kind: "stable" },
        isSuppressed: false,
        geometryAtBottom: false,
        readingAnchor: null,
      }),
    ).toBe(false);
    expect(
      isScrollSettled({
        authority: { kind: "navigating", promptIndex: 0 },
        layout: { kind: "stable" },
        isSuppressed: false,
        geometryAtBottom: false,
        readingAnchor: null,
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
          readingAnchor: null,
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
          readingAnchor: null,
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
          projectAtBottom({
            authority,
            layout: { kind: "stable" },
            isSuppressed: false,
            geometryAtBottom: true,
            readingAnchor: null,
          }),
        ).toBe(true);
        expect(
          projectAtBottom({
            authority,
            layout: { kind: "stable" },
            isSuppressed: false,
            geometryAtBottom: false,
            readingAnchor: null,
          }),
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

  describe("setReadingAnchor", () => {
    it("records the sampled anchor without notifying subscribers", () => {
      const m = createScrollStateMachine();
      const listener = vi.fn();
      m.subscribe(listener);

      m.setReadingAnchor({ messageIndex: 3, viewportOffset: 120 });

      expect(m.getState().readingAnchor).toEqual({ messageIndex: 3, viewportOffset: 120 });
      // It is a sample read only by projectReflow inside the resize observer —
      // never a selector input — so it must not churn a re-render per scroll frame.
      expect(listener).not.toHaveBeenCalled();
    });

    it("clears the anchor when set to null", () => {
      const m = createScrollStateMachine();
      m.setReadingAnchor({ messageIndex: 1, viewportOffset: 0 });
      m.setReadingAnchor(null);
      expect(m.getState().readingAnchor).toBeNull();
    });
  });

  describe("projectReflow", () => {
    it("pins to the bottom while following (streaming or not)", () => {
      expect(projectReflow(stateWith({ authority: { kind: "following" } }), true)).toEqual({ kind: "pinBottom" });
      expect(projectReflow(stateWith({ authority: { kind: "following" } }), false)).toEqual({ kind: "pinBottom" });
    });

    it("holds the anchored turn at the top while anchoringTurn", () => {
      expect(projectReflow(stateWith({ authority: { kind: "anchoringTurn", anchorIndex: 4 } }), true)).toEqual({
        kind: "holdTurn",
        anchorIndex: 4,
      });
    });

    it("leaves scrollTop to the owner while restoring or navigating", () => {
      expect(projectReflow(stateWith({ authority: { kind: "restoring", taskId: "t" } }), false)).toEqual({
        kind: "ignore",
      });
      expect(projectReflow(stateWith({ authority: { kind: "navigating", promptIndex: 0 } }), false)).toEqual({
        kind: "ignore",
      });
    });

    it("pins to the bottom while idle (not streaming) and userControlled at the bottom", () => {
      expect(
        projectReflow(stateWith({ authority: { kind: "userControlled" }, geometryAtBottom: true }), false),
      ).toEqual({ kind: "pinBottom" });
    });

    it("does NOT pin a disengaged user mid-stream, even within the at-bottom threshold", () => {
      // While streaming, userControlled means deliberately disengaged from the
      // live tail — content growth must not pull them back to the bottom.
      expect(projectReflow(stateWith({ authority: { kind: "userControlled" }, geometryAtBottom: true }), true)).toEqual(
        {
          kind: "ignore",
        },
      );
    });

    it("holds the reading anchor while userControlled, scrolled up, with an anchor sampled", () => {
      const anchor = { messageIndex: 2, viewportOffset: 277 };
      expect(
        projectReflow(
          stateWith({ authority: { kind: "userControlled" }, geometryAtBottom: false, readingAnchor: anchor }),
          false,
        ),
      ).toEqual({ kind: "holdAnchor", anchor });
    });

    it("ignores while userControlled, scrolled up, before any anchor is sampled", () => {
      expect(
        projectReflow(
          stateWith({ authority: { kind: "userControlled" }, geometryAtBottom: false, readingAnchor: null }),
          false,
        ),
      ).toEqual({ kind: "ignore" });
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
