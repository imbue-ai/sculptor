import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";

import { PluginContext } from "../PluginContext.tsx";
import { useOpenNewWorkspaceModal, usePluginSetting, usePluginSettings, useSetPluginSetting } from "./hooks.ts";

type Store = ReturnType<typeof createStore>;

// Wrap in the jotai store plus the host's plugin identity, mirroring how the
// host mounts plugin components — the settings hooks derive their storage
// namespace from PluginContext.
const createWrapper = (store: Store, pluginId: string) => {
  return ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <PluginContext.Provider value={{ pluginId }}>{children}</PluginContext.Provider>
    </Provider>
  );
};

afterEach(() => {
  cleanup();
  // The per-key setting atoms persist to localStorage, so wipe it between
  // tests. This alone does not isolate the atoms themselves: the module-level
  // atomFamily cache outlives each test's store, and a cached atom reads
  // storage only once, at creation — so test independence also relies on no
  // two tests reusing the same (pluginId, key) pair.
  window.localStorage.clear();
});

describe("useOpenNewWorkspaceModal", () => {
  it("opens the modal with the given seeds and create callback", () => {
    const store = createStore();
    const onCreated = vi.fn();
    const { result } = renderHook(() => useOpenNewWorkspaceModal(), {
      wrapper: createWrapper(store, "test-plugin"),
    });

    act(() => {
      result.current({ initialTitle: "Fix the bug", initialPrompt: "Please fix it", onCreated });
    });

    expect(store.get(newWorkspaceModalAtom)).toEqual({
      open: true,
      initialTitle: "Fix the bug",
      initialPrompt: "Please fix it",
      onWorkspaceCreated: onCreated,
    });
  });

  it("opens the modal unseeded when called with no options", () => {
    const store = createStore();
    const { result } = renderHook(() => useOpenNewWorkspaceModal(), {
      wrapper: createWrapper(store, "test-plugin"),
    });

    act(() => {
      result.current();
    });

    const state = store.get(newWorkspaceModalAtom);
    expect(state.open).toBe(true);
    expect(state.initialTitle).toBeUndefined();
    expect(state.initialPrompt).toBeUndefined();
    expect(state.onWorkspaceCreated).toBeUndefined();
  });
});

describe("useSetPluginSetting", () => {
  it("writes are seen reactively by usePluginSettings and usePluginSetting", () => {
    const store = createStore();
    const { result } = renderHook(
      () => ({
        set: useSetPluginSetting(),
        settings: usePluginSettings(["ws:1", "ws:2"]),
        single: usePluginSetting("ws:1")[0],
      }),
      { wrapper: createWrapper(store, "test-plugin") },
    );

    expect(result.current.settings.get("ws:1")).toBe("");

    act(() => {
      result.current.set("ws:1", "linked");
    });

    expect(result.current.settings.get("ws:1")).toBe("linked");
    expect(result.current.settings.get("ws:2")).toBe("");
    expect(result.current.single).toBe("linked");
  });

  it("namespaces writes by the calling plugin's id", () => {
    const store = createStore();
    const { result } = renderHook(() => useSetPluginSetting(), {
      wrapper: createWrapper(store, "plugin-a"),
    });

    act(() => {
      result.current("shared-key", "a-value");
    });

    // A different plugin reading the same key must not see plugin-a's value.
    const other = renderHook(() => usePluginSettings(["shared-key"]), {
      wrapper: createWrapper(store, "plugin-b"),
    });
    expect(other.result.current.get("shared-key")).toBe("");
    expect(window.localStorage.getItem("sculptor-plugin:plugin-a:shared-key")).toBe(JSON.stringify("a-value"));
  });
});
