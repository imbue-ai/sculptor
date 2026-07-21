import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { SavedLayout } from "./persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT, SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import {
  appliedLayoutIdAtom,
  defaultLayoutAtom,
  defaultLayoutIdAtom,
  layoutMruAtom,
  resolvedLayoutsAtom,
  savedLayoutsAtom,
} from "./savedLayoutAtoms.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID, SYSTEM_LAYOUTS } from "./systemDefaultLayout.ts";

function makeLayout(id: string, overrides: Partial<SavedLayout> = {}): SavedLayout {
  return {
    id,
    name: id,
    version: SAVED_LAYOUT_VERSION,
    captured: SYSTEM_DEFAULT_LAYOUT.captured,
    ...overrides,
  };
}

beforeEach(() => {
  localStorage.clear();
});

describe("global saved-layout slices", () => {
  it("default to empty / System Default and write through the global store", () => {
    const store = createStore();
    expect(store.get(savedLayoutsAtom)).toEqual([]);
    expect(store.get(defaultLayoutIdAtom)).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
    expect(store.get(layoutMruAtom)).toEqual([]);

    const focused = makeLayout("focused");
    store.set(savedLayoutsAtom, [focused]);
    store.set(defaultLayoutIdAtom, "focused");
    store.set(layoutMruAtom, ["focused", SYSTEM_DEFAULT_LAYOUT_ID]);

    expect(store.get(savedLayoutsAtom)).toEqual([focused]);
    expect(store.get(defaultLayoutIdAtom)).toBe("focused");
    expect(store.get(layoutMruAtom)).toEqual(["focused", SYSTEM_DEFAULT_LAYOUT_ID]);
  });
});

describe("appliedLayoutIdAtom (per-workspace)", () => {
  it("reads and writes the active workspace's pointer in isolation", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-a");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });
    expect(store.get(appliedLayoutIdAtom)).toBeUndefined();

    store.set(appliedLayoutIdAtom, "focused");
    expect(store.get(appliedLayoutIdAtom)).toBe("focused");

    // A different workspace has its own (unset) pointer.
    store.set(activeWorkspaceIdAtom, "ws-b");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });
    expect(store.get(appliedLayoutIdAtom)).toBeUndefined();

    store.set(activeWorkspaceIdAtom, "ws-a");
    expect(store.get(appliedLayoutIdAtom)).toBe("focused");
  });
});

describe("resolvedLayoutsAtom", () => {
  it("puts the built-in system layouts first and appends saved layouts, skipping unreadable versions", () => {
    const store = createStore();
    const good = makeLayout("good");
    const future = makeLayout("future", { version: SAVED_LAYOUT_VERSION + 1 });
    store.set(savedLayoutsAtom, [good, future]);

    const resolved = store.get(resolvedLayoutsAtom);
    // System Default + the task presets, in order, then the readable saved layout.
    expect(resolved.map((layout) => layout.id)).toEqual([...SYSTEM_LAYOUTS.map((layout) => layout.id), "good"]);
    expect(resolved[0].id).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
  });
});

describe("defaultLayoutAtom", () => {
  it("resolves the pointer, falling back to System Default when it names nothing", () => {
    const store = createStore();
    const focused = makeLayout("focused");
    store.set(savedLayoutsAtom, [focused]);

    store.set(defaultLayoutIdAtom, "focused");
    expect(store.get(defaultLayoutAtom).id).toBe("focused");

    // A pointer at a since-deleted layout resolves back to System Default.
    store.set(defaultLayoutIdAtom, "deleted-id");
    expect(store.get(defaultLayoutAtom).id).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
  });
});
