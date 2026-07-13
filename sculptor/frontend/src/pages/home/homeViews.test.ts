import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import { extensionHomeViewsAtom } from "~/extensions/extensionRegistry.ts";

import {
  BUILTIN_HOME_VIEW_ID,
  effectiveHomeViewIdAtom,
  homeViewOptionsAtom,
  resolveEffectiveHomeViewId,
  selectedHomeViewAtom,
} from "./homeViews.ts";

describe("resolveEffectiveHomeViewId", () => {
  it("keeps the selection when it is still available", () => {
    expect(resolveEffectiveHomeViewId("tasks-board", [BUILTIN_HOME_VIEW_ID, "tasks-board"])).toBe("tasks-board");
  });

  it("falls back to the built-in view when the selection is gone", () => {
    // e.g. the extension that registered "tasks-board" was unloaded
    expect(resolveEffectiveHomeViewId("tasks-board", [BUILTIN_HOME_VIEW_ID])).toBe(BUILTIN_HOME_VIEW_ID);
  });

  it("returns the built-in view when it is the only option", () => {
    expect(resolveEffectiveHomeViewId(BUILTIN_HOME_VIEW_ID, [BUILTIN_HOME_VIEW_ID])).toBe(BUILTIN_HOME_VIEW_ID);
  });
});

describe("home view atoms", () => {
  const TasksView = (): null => null;

  beforeEach(() => {
    localStorage.clear();
  });

  it("offers only the built-in view, selected, when no extension contributes one", () => {
    const store = createStore();
    expect(store.get(homeViewOptionsAtom).map((option) => option.id)).toEqual([BUILTIN_HOME_VIEW_ID]);
    expect(store.get(effectiveHomeViewIdAtom)).toBe(BUILTIN_HOME_VIEW_ID);
  });

  it("appends extension views to the switcher but keeps the built-in active by default", () => {
    const store = createStore();
    store.set(extensionHomeViewsAtom, [{ id: "tasks", title: "Tasks board", component: TasksView }]);
    expect(store.get(homeViewOptionsAtom).map((option) => option.id)).toEqual([BUILTIN_HOME_VIEW_ID, "tasks"]);
    expect(store.get(effectiveHomeViewIdAtom)).toBe(BUILTIN_HOME_VIEW_ID);
  });

  it("honors a stored selection of a registered extension view", () => {
    const store = createStore();
    store.set(extensionHomeViewsAtom, [{ id: "tasks", title: "Tasks board", component: TasksView }]);
    store.set(selectedHomeViewAtom, "tasks");
    expect(store.get(effectiveHomeViewIdAtom)).toBe("tasks");
  });

  it("falls back to the built-in view when the selected extension view is unregistered", () => {
    const store = createStore();
    store.set(extensionHomeViewsAtom, [{ id: "tasks", title: "Tasks board", component: TasksView }]);
    store.set(selectedHomeViewAtom, "tasks");
    expect(store.get(effectiveHomeViewIdAtom)).toBe("tasks");

    // The extension is unloaded; the selection persists but no longer resolves.
    store.set(extensionHomeViewsAtom, []);
    expect(store.get(effectiveHomeViewIdAtom)).toBe(BUILTIN_HOME_VIEW_ID);
  });

  it("keeps option ids unique when an extension view claims the reserved built-in id", () => {
    // registerHomeView rejects this id, but guard the options atom too: a stray
    // entry must not produce duplicate ids (duplicate React keys / segment values).
    const store = createStore();
    store.set(extensionHomeViewsAtom, [
      { id: BUILTIN_HOME_VIEW_ID, title: "Hijacked", component: TasksView },
      { id: "tasks", title: "Tasks board", component: TasksView },
    ]);
    const ids = store.get(homeViewOptionsAtom).map((option) => option.id);
    expect(ids).toEqual([BUILTIN_HOME_VIEW_ID, "tasks"]);
    // The built-in title wins the reserved id, not the extension's "Hijacked".
    expect(store.get(homeViewOptionsAtom)[0].title).toBe("Recent workspaces");
    expect(store.get(effectiveHomeViewIdAtom)).toBe(BUILTIN_HOME_VIEW_ID);
  });
});
