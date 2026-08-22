import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import { isSmoothStreamingEnabledAtomFamily, isSmoothStreamingViewportVisibleAtomFamily } from "./smoothStreaming.ts";

describe("smooth streaming viewport atoms", () => {
  it("default to visible/enabled for a task with no observed state", () => {
    const store = createStore();
    expect(store.get(isSmoothStreamingViewportVisibleAtomFamily("task-1"))).toBe(true);
    // User preference defaults to true (no userConfig set), so enabled follows visibility.
    expect(store.get(isSmoothStreamingEnabledAtomFamily("task-1"))).toBe(true);
  });

  it("keeps per-task visibility independent (multi-panel gate does not leak)", () => {
    const store = createStore();

    // Task A scrolls off-screen; task B stays visible.
    store.set(isSmoothStreamingViewportVisibleAtomFamily("task-a"), false);

    expect(store.get(isSmoothStreamingViewportVisibleAtomFamily("task-a"))).toBe(false);
    expect(store.get(isSmoothStreamingViewportVisibleAtomFamily("task-b"))).toBe(true);

    // The derived enabled atom follows each task's own visibility, so the
    // off-screen panel does not disable smooth streaming for the visible one.
    expect(store.get(isSmoothStreamingEnabledAtomFamily("task-a"))).toBe(false);
    expect(store.get(isSmoothStreamingEnabledAtomFamily("task-b"))).toBe(true);
  });
});
