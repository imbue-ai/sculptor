import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { AlphaScrollPosition } from "./alphaScroll";
import { alphaScrollPositionAtomFamily } from "./alphaScroll";

const position = (overrides?: Partial<AlphaScrollPosition>): AlphaScrollPosition => ({
  firstVisibleMessageId: "msg-42",
  pixelOffset: 17,
  distanceFromBottom: 480,
  ...overrides,
});

// The atomFamily caches its atoms for the module's lifetime, and `getOnInit`
// reads sessionStorage when the atom is *created*. Each test therefore uses a
// unique taskId, so the atom creation happens inside the test — after that
// test's sessionStorage setup — matching what a real page load does (fresh
// module, storage already populated).
describe("alphaScrollPositionAtomFamily", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("returns null when no position has been stored", () => {
    const store = createStore();
    expect(store.get(alphaScrollPositionAtomFamily("fresh-task"))).toBeNull();
  });

  it("persists writes to sessionStorage under the task-keyed key", () => {
    const store = createStore();
    const saved = position();

    store.set(alphaScrollPositionAtomFamily("write-task"), saved);

    expect(JSON.parse(sessionStorage.getItem("sculptor-alpha-scroll:write-task") ?? "")).toEqual(saved);
  });

  it("rehydrates a stored position on the first read after a reload", () => {
    const saved = position();
    sessionStorage.setItem("sculptor-alpha-scroll:reload-task", JSON.stringify(saved));

    // A fresh store stands in for the reloaded page: nothing has been written
    // through jotai in this "session", so the value can only come from
    // sessionStorage via getOnInit. Without getOnInit the first synchronous
    // read — which the pre-paint mount restore depends on — would be null.
    const store = createStore();
    expect(store.get(alphaScrollPositionAtomFamily("reload-task"))).toEqual(saved);
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
});
