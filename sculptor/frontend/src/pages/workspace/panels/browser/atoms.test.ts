import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { browserPanelStateAtomFamily, DEFAULT_BROWSER_PANEL_STATE } from "./atoms";

beforeEach(() => localStorage.clear());
afterEach(() => {
  localStorage.clear();
  browserPanelStateAtomFamily.remove("A");
  browserPanelStateAtomFamily.remove("B");
});

describe("browserPanelStateAtomFamily", () => {
  it("yields the default state for a fresh workspace id", () => {
    const store = createStore();
    const state = store.get(browserPanelStateAtomFamily("A"));
    expect(state).toEqual(DEFAULT_BROWSER_PANEL_STATE);
  });

  it("round-trips an updated state", () => {
    const store = createStore();
    const atom = browserPanelStateAtomFamily("A");
    store.set(atom, { currentUrl: "https://example.com" });
    expect(store.get(atom)).toEqual({ currentUrl: "https://example.com" });
  });

  it("keeps state isolated per workspace id", () => {
    const store = createStore();
    const atomA = browserPanelStateAtomFamily("A");
    const atomB = browserPanelStateAtomFamily("B");
    store.set(atomA, { currentUrl: "https://a.example" });
    expect(store.get(atomA).currentUrl).toBe("https://a.example");
    expect(store.get(atomB)).toEqual(DEFAULT_BROWSER_PANEL_STATE);
  });
});
