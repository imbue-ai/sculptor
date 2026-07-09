import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";

import { ExtensionContext } from "../ExtensionContext.tsx";
import {
  useExtensionSetting,
  useExtensionSettings,
  useOpenNewWorkspaceModal,
  useSetExtensionSetting,
} from "./hooks.ts";

type Store = ReturnType<typeof createStore>;

// Wrap in the jotai store plus the host's extension identity, mirroring how the
// host mounts extension components — the settings hooks derive their storage
// namespace from ExtensionContext.
const createWrapper = (store: Store, extensionId: string) => {
  return ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <ExtensionContext.Provider value={{ extensionId }}>{children}</ExtensionContext.Provider>
    </Provider>
  );
};

afterEach(() => {
  cleanup();
  // The per-key setting atoms persist to localStorage, so wipe it between
  // tests. This alone does not isolate the atoms themselves: the module-level
  // atomFamily cache outlives each test's store, and a cached atom reads
  // storage only once, at creation — so test independence also relies on no
  // two tests reusing the same (extensionId, key) pair.
  window.localStorage.clear();
});

describe("useOpenNewWorkspaceModal", () => {
  it("opens the modal with the given seeds and create callback", () => {
    const store = createStore();
    const onCreated = vi.fn();
    const { result } = renderHook(() => useOpenNewWorkspaceModal(), {
      wrapper: createWrapper(store, "test-extension"),
    });

    act(() => {
      result.current({
        initialTitle: "Fix the bug",
        initialPrompt: "Please fix it",
        initialBranchName: "fix/the-bug",
        onCreated,
      });
    });

    expect(store.get(newWorkspaceModalAtom)).toEqual({
      open: true,
      initialTitle: "Fix the bug",
      initialPrompt: "Please fix it",
      initialBranchName: "fix/the-bug",
      onWorkspaceCreated: onCreated,
    });
  });

  it("opens the modal unseeded when called with no options", () => {
    const store = createStore();
    const { result } = renderHook(() => useOpenNewWorkspaceModal(), {
      wrapper: createWrapper(store, "test-extension"),
    });

    act(() => {
      result.current();
    });

    const state = store.get(newWorkspaceModalAtom);
    expect(state.open).toBe(true);
    expect(state.initialTitle).toBeUndefined();
    expect(state.initialPrompt).toBeUndefined();
    expect(state.initialBranchName).toBeUndefined();
    expect(state.onWorkspaceCreated).toBeUndefined();
  });
});

describe("useSetExtensionSetting", () => {
  it("writes are seen reactively by useExtensionSettings and useExtensionSetting", () => {
    const store = createStore();
    const { result } = renderHook(
      () => ({
        set: useSetExtensionSetting(),
        settings: useExtensionSettings(["ws:1", "ws:2"]),
        single: useExtensionSetting("ws:1")[0],
      }),
      { wrapper: createWrapper(store, "test-extension") },
    );

    expect(result.current.settings.get("ws:1")).toBe("");

    act(() => {
      result.current.set("ws:1", "linked");
    });

    expect(result.current.settings.get("ws:1")).toBe("linked");
    expect(result.current.settings.get("ws:2")).toBe("");
    expect(result.current.single).toBe("linked");
  });

  it("namespaces writes by the calling extension's id", () => {
    const store = createStore();
    const { result } = renderHook(() => useSetExtensionSetting(), {
      wrapper: createWrapper(store, "extension-a"),
    });

    act(() => {
      result.current("shared-key", "a-value");
    });

    // A different extension reading the same key must not see extension-a's value.
    const other = renderHook(() => useExtensionSettings(["shared-key"]), {
      wrapper: createWrapper(store, "extension-b"),
    });
    expect(other.result.current.get("shared-key")).toBe("");
    expect(window.localStorage.getItem("sculptor-extension:extension-a:shared-key")).toBe(JSON.stringify("a-value"));
  });
});
