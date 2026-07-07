import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { AlphaScrollPosition } from "./alphaScroll";
import { alphaScrollPositionAtomFamily, MAX_PERSISTED_SCROLL_POSITIONS } from "./alphaScroll";

const position = (overrides?: Partial<AlphaScrollPosition>): AlphaScrollPosition => ({
  firstVisibleMessageId: "msg-42",
  pixelOffset: 17,
  distanceFromBottom: 480,
  savedAtMs: 1_000_000,
  ...overrides,
});

// The atomFamily caches its atoms for the module's lifetime, and `getOnInit`
// reads localStorage when the atom is *created*. Each test therefore uses a
// unique taskId, so the atom creation happens inside the test — after that
// test's localStorage setup — matching what a real app start does (fresh
// module, storage already populated).
describe("alphaScrollPositionAtomFamily", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when no position has been stored", () => {
    const store = createStore();
    expect(store.get(alphaScrollPositionAtomFamily("fresh-task"))).toBeNull();
  });

  it("persists writes to localStorage under the task-keyed key", () => {
    const store = createStore();
    const saved = position();

    store.set(alphaScrollPositionAtomFamily("write-task"), saved);

    expect(JSON.parse(localStorage.getItem("sculptor-alpha-scroll:write-task") ?? "")).toEqual(saved);
  });

  it("rehydrates a stored position on the first read after an app restart", () => {
    const saved = position();
    localStorage.setItem("sculptor-alpha-scroll:restart-task", JSON.stringify(saved));

    // A fresh store stands in for the restarted app: nothing has been written
    // through jotai in this process, so the value can only come from
    // localStorage via getOnInit. Without getOnInit the first synchronous
    // read — which the pre-paint mount restore depends on — would be null.
    const store = createStore();
    expect(store.get(alphaScrollPositionAtomFamily("restart-task"))).toEqual(saved);
  });

  it("keeps positions isolated per task", () => {
    const store = createStore();
    const first = position();
    const second = position({ firstVisibleMessageId: "msg-7", pixelOffset: 3, distanceFromBottom: 0 });

    store.set(alphaScrollPositionAtomFamily("task-a"), first);
    store.set(alphaScrollPositionAtomFamily("task-b"), second);

    expect(store.get(alphaScrollPositionAtomFamily("task-a"))).toEqual(first);
    expect(store.get(alphaScrollPositionAtomFamily("task-b"))).toEqual(second);
  });

  it("evicts the oldest-saved positions once the cap is exceeded", () => {
    const store = createStore();

    // Fill to the cap with strictly increasing save times, then write one more.
    for (let i = 0; i <= MAX_PERSISTED_SCROLL_POSITIONS; i++) {
      store.set(alphaScrollPositionAtomFamily(`evict-task-${i}`), position({ savedAtMs: i + 1 }));
    }

    const persistedKeys: Array<string> = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith("sculptor-alpha-scroll:")) persistedKeys.push(key);
    }
    expect(persistedKeys).toHaveLength(MAX_PERSISTED_SCROLL_POSITIONS);
    // The oldest entry made way; the newest write survives.
    expect(localStorage.getItem("sculptor-alpha-scroll:evict-task-0")).toBeNull();
    expect(localStorage.getItem(`sculptor-alpha-scroll:evict-task-${MAX_PERSISTED_SCROLL_POSITIONS}`)).not.toBeNull();
  });

  it("evicts entries missing savedAtMs before timestamped ones", () => {
    const store = createStore();
    localStorage.setItem("sculptor-alpha-scroll:legacy-task", JSON.stringify(position({ savedAtMs: undefined })));

    for (let i = 0; i < MAX_PERSISTED_SCROLL_POSITIONS; i++) {
      store.set(alphaScrollPositionAtomFamily(`fill-task-${i}`), position({ savedAtMs: i + 1 }));
    }

    expect(localStorage.getItem("sculptor-alpha-scroll:legacy-task")).toBeNull();
    expect(localStorage.getItem("sculptor-alpha-scroll:fill-task-0")).not.toBeNull();
  });
});
