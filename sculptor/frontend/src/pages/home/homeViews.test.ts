import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import { pluginHomeViewsAtom } from "~/plugins/pluginRegistry.ts";

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
    // e.g. the plugin that registered "tasks-board" was unloaded
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

  it("offers only the built-in view, selected, when no plugin contributes one", () => {
    const store = createStore();
    expect(store.get(homeViewOptionsAtom).map((option) => option.id)).toEqual([BUILTIN_HOME_VIEW_ID]);
    expect(store.get(effectiveHomeViewIdAtom)).toBe(BUILTIN_HOME_VIEW_ID);
  });

  it("appends plugin views to the switcher but keeps the built-in active by default", () => {
    const store = createStore();
    store.set(pluginHomeViewsAtom, [{ id: "tasks", title: "Tasks board", component: TasksView }]);
    expect(store.get(homeViewOptionsAtom).map((option) => option.id)).toEqual([BUILTIN_HOME_VIEW_ID, "tasks"]);
    expect(store.get(effectiveHomeViewIdAtom)).toBe(BUILTIN_HOME_VIEW_ID);
  });

  it("honors a stored selection of a registered plugin view", () => {
    const store = createStore();
    store.set(pluginHomeViewsAtom, [{ id: "tasks", title: "Tasks board", component: TasksView }]);
    store.set(selectedHomeViewAtom, "tasks");
    expect(store.get(effectiveHomeViewIdAtom)).toBe("tasks");
  });

  it("falls back to the built-in view when the selected plugin view is unregistered", () => {
    const store = createStore();
    store.set(pluginHomeViewsAtom, [{ id: "tasks", title: "Tasks board", component: TasksView }]);
    store.set(selectedHomeViewAtom, "tasks");
    expect(store.get(effectiveHomeViewIdAtom)).toBe("tasks");

    // The plugin is unloaded; the selection persists but no longer resolves.
    store.set(pluginHomeViewsAtom, []);
    expect(store.get(effectiveHomeViewIdAtom)).toBe(BUILTIN_HOME_VIEW_ID);
  });
});
