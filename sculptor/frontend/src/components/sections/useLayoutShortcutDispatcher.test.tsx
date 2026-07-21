import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { UserConfig } from "~/api";
import { layoutShortcutBindingId } from "~/common/keybindings/layoutShortcuts.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";

import type { SavedLayout } from "./persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT, SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import { appliedLayoutIdAtom, layoutMruAtom, savedLayoutsAtom } from "./savedLayoutAtoms.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT } from "./systemDefaultLayout.ts";
import { useLayoutShortcutDispatcher } from "./useLayoutShortcutDispatcher.ts";

function makeLayout(id: string): SavedLayout {
  return { id, name: id, version: SAVED_LAYOUT_VERSION, captured: SYSTEM_DEFAULT_LAYOUT.captured };
}

function withKeybindings(bindings: Record<string, string | null>): UserConfig {
  return { keybindings: bindings } as unknown as UserConfig;
}

describe("useLayoutShortcutDispatcher", () => {
  let store: ReturnType<typeof createStore>;

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );

  // "Alt+1" carries no platform-remapped modifier, so a single dispatched event
  // matches identically on macOS and Linux/Windows (unlike a "Meta+…" chord).
  const dispatchKey = (init: KeyboardEventInit): KeyboardEvent => {
    const event = new KeyboardEvent("keydown", { cancelable: true, ...init });
    act(() => {
      window.dispatchEvent(event);
    });
    return event;
  };

  beforeEach(() => {
    localStorage.clear();
    store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-1");
    store.set(workspaceLayoutAtom, EMPTY_WORKSPACE_LAYOUT);
  });

  afterEach(() => {
    // Unmount every hook so its window keydown listener detaches — a leaked
    // listener from an earlier test would still fire on later dispatches.
    cleanup();
    // Clear any overlay node a test mounted so the DOM-scanning guard starts clean.
    document.body.innerHTML = "";
  });

  it("applies the bound layout and prevents default on a matching chord", () => {
    store.set(savedLayoutsAtom, [makeLayout("a")]);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));
    renderHook(() => useLayoutShortcutDispatcher(), { wrapper });

    const event = dispatchKey({ key: "1", altKey: true });

    expect(store.get(appliedLayoutIdAtom)).toBe("a");
    expect(store.get(layoutMruAtom)[0]).toBe("a");
    expect(event.defaultPrevented).toBe(true);
  });

  it("ignores a chord that is not bound to any layout", () => {
    store.set(savedLayoutsAtom, [makeLayout("a")]);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));
    renderHook(() => useLayoutShortcutDispatcher(), { wrapper });

    const event = dispatchKey({ key: "2", altKey: true });

    expect(store.get(appliedLayoutIdAtom)).toBeUndefined();
    expect(event.defaultPrevented).toBe(false);
  });

  it("does not fire while a dismissible overlay is open", () => {
    store.set(savedLayoutsAtom, [makeLayout("a")]);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));
    renderHook(() => useLayoutShortcutDispatcher(), { wrapper });

    // The guard scans the DOM for an open Radix dialog, so a matching node is
    // enough to simulate an overlay being on top.
    const overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("data-state", "open");
    document.body.appendChild(overlay);

    const event = dispatchKey({ key: "1", altKey: true });

    expect(store.get(appliedLayoutIdAtom)).toBeUndefined();
    expect(event.defaultPrevented).toBe(false);
  });

  it("does nothing for a shortcut bound to a layout that no longer exists", () => {
    // The chord is bound to "ghost", but no such layout resolves. The bindings the
    // dispatcher reads are themselves derived from the resolvable layouts, so a
    // dangling binding matches nothing — no apply runs and nothing throws.
    store.set(savedLayoutsAtom, []);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("ghost")]: "Alt+1" }));
    renderHook(() => useLayoutShortcutDispatcher(), { wrapper });

    const event = dispatchKey({ key: "1", altKey: true });

    expect(store.get(appliedLayoutIdAtom)).toBeUndefined();
    expect(event.defaultPrevented).toBe(false);
  });

  it("removes the keydown listener on unmount", () => {
    store.set(savedLayoutsAtom, [makeLayout("a")]);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));
    const { unmount } = renderHook(() => useLayoutShortcutDispatcher(), { wrapper });

    unmount();
    const event = dispatchKey({ key: "1", altKey: true });

    expect(store.get(appliedLayoutIdAtom)).toBeUndefined();
    expect(event.defaultPrevented).toBe(false);
  });
});
