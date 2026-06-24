import { describe, expect, it } from "vitest";

import type { ScrollAuthority, ScrollEvent } from "../scrollAuthority.ts";
import { initialAuthority, nextAuthority } from "../scrollAuthority.ts";

const ALL_STATES: ReadonlyArray<ScrollAuthority> = [
  { kind: "userControlled" },
  { kind: "restoring", taskId: "t" },
  { kind: "anchoringTurn", anchorIndex: 3 },
  { kind: "following" },
  { kind: "navigating", promptIndex: 1 },
];

describe("nextAuthority", () => {
  it("starts userControlled", () => {
    expect(initialAuthority).toEqual({ kind: "userControlled" });
  });

  describe("global transitions valid from every state", () => {
    it.each(ALL_STATES)("userScrolled returns control to the user (from %o)", (state) => {
      expect(nextAuthority(state, { kind: "userScrolled" })).toEqual({ kind: "userControlled" });
    });

    it.each(ALL_STATES)("taskSwitched begins restoring (from %o)", (state) => {
      expect(nextAuthority(state, { kind: "taskSwitched", taskId: "next" })).toEqual({
        kind: "restoring",
        taskId: "next",
      });
    });
  });

  describe("from userControlled", () => {
    const s: ScrollAuthority = { kind: "userControlled" };
    it("newUserTurn -> anchoringTurn", () => {
      expect(nextAuthority(s, { kind: "newUserTurn", index: 4 })).toEqual({ kind: "anchoringTurn", anchorIndex: 4 });
    });
    it("reachedBottom -> following", () => {
      expect(nextAuthority(s, { kind: "reachedBottom" })).toEqual({ kind: "following" });
    });
    it("navStarted -> navigating", () => {
      expect(nextAuthority(s, { kind: "navStarted", promptIndex: 2 })).toEqual({ kind: "navigating", promptIndex: 2 });
    });
    it("ignores completion events (same reference)", () => {
      expect(nextAuthority(s, { kind: "turnAnchored" })).toBe(s);
      expect(nextAuthority(s, { kind: "restoreSettled" })).toBe(s);
    });
  });

  describe("from restoring", () => {
    const s: ScrollAuthority = { kind: "restoring", taskId: "t" };
    it("restoreSettled -> userControlled", () => {
      expect(nextAuthority(s, { kind: "restoreSettled" })).toEqual({ kind: "userControlled" });
    });
    it("ignores auto-scroll events while restoring (same reference)", () => {
      expect(nextAuthority(s, { kind: "newUserTurn", index: 1 })).toBe(s);
      expect(nextAuthority(s, { kind: "reachedBottom" })).toBe(s);
    });
  });

  describe("from anchoringTurn", () => {
    const s: ScrollAuthority = { kind: "anchoringTurn", anchorIndex: 2 };
    it("turnAnchored -> following", () => {
      expect(nextAuthority(s, { kind: "turnAnchored" })).toEqual({ kind: "following" });
    });
    it("ignores unrelated events (same reference)", () => {
      expect(nextAuthority(s, { kind: "streamingStopped" })).toBe(s);
    });
  });

  describe("from following", () => {
    const s: ScrollAuthority = { kind: "following" };
    it("streamingStopped -> userControlled", () => {
      expect(nextAuthority(s, { kind: "streamingStopped" })).toEqual({ kind: "userControlled" });
    });
    it("newUserTurn -> anchoringTurn (a new turn while following)", () => {
      expect(nextAuthority(s, { kind: "newUserTurn", index: 7 })).toEqual({ kind: "anchoringTurn", anchorIndex: 7 });
    });
  });

  describe("from navigating", () => {
    const s: ScrollAuthority = { kind: "navigating", promptIndex: 1 };
    it("navMoved -> navigating with the new prompt index", () => {
      expect(nextAuthority(s, { kind: "navMoved", promptIndex: 2 })).toEqual({ kind: "navigating", promptIndex: 2 });
    });
    it("navEnded -> userControlled", () => {
      expect(nextAuthority(s, { kind: "navEnded" })).toEqual({ kind: "userControlled" });
    });
    it("ignores auto-scroll events while navigating (same reference)", () => {
      expect(nextAuthority(s, { kind: "reachedBottom" })).toBe(s);
    });
  });

  it("userScrolled from userControlled is an identity no-op", () => {
    const s: ScrollAuthority = { kind: "userControlled" };
    expect(nextAuthority(s, { kind: "userScrolled" })).toBe(s);
  });

  it("never throws for any (state, event) pair", () => {
    const events: ReadonlyArray<ScrollEvent> = [
      { kind: "taskSwitched", taskId: "x" },
      { kind: "restoreSettled" },
      { kind: "userScrolled" },
      { kind: "newUserTurn", index: 0 },
      { kind: "turnAnchored" },
      { kind: "reachedBottom" },
      { kind: "streamingStopped" },
      { kind: "navStarted", promptIndex: 0 },
      { kind: "navMoved", promptIndex: 0 },
      { kind: "navEnded" },
    ];
    for (const state of ALL_STATES) {
      for (const event of events) {
        expect(() => nextAuthority(state, event)).not.toThrow();
      }
    }
  });
});
