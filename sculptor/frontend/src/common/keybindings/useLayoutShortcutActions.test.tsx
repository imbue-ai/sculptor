import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { UserConfig } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import type { SavedLayout } from "~/components/sections/persistence/types.ts";
import { SAVED_LAYOUT_VERSION } from "~/components/sections/persistence/types.ts";
import { savedLayoutsAtom } from "~/components/sections/savedLayoutAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT } from "~/components/sections/systemDefaultLayout.ts";

import { layoutShortcutBindingId, type NamedBinding } from "./layoutShortcuts.ts";
import { useLayoutBindingConflict, useSetLayoutShortcut } from "./useLayoutShortcutActions.ts";

// useUserConfig persists through the generated API SDK. Mock the SDK module the
// barrel re-exports so writes stay in memory; the echo below makes the optimistic
// update stick instead of being reverted, letting us assert the persisted config.
const { mockUpdateUserConfig } = vi.hoisted(() => ({ mockUpdateUserConfig: vi.fn() }));

vi.mock("~/api/sdk.gen", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getUserConfig: vi.fn().mockResolvedValue({ data: null }),
    updateUserConfig: mockUpdateUserConfig,
  };
});

function makeLayout(id: string): SavedLayout {
  return { id, name: id, version: SAVED_LAYOUT_VERSION, captured: SYSTEM_DEFAULT_LAYOUT.captured };
}

function withKeybindings(bindings: Record<string, string | null>): UserConfig {
  return { keybindings: bindings } as unknown as UserConfig;
}

const wrapperFor =
  (store: ReturnType<typeof createStore>) =>
  ({ children }: { children: ReactNode }): ReactElement => <Provider store={store}>{children}</Provider>;

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  mockUpdateUserConfig.mockImplementation((options: { body: { userConfig: Record<string, unknown> } }) =>
    Promise.resolve({ data: options.body.userConfig }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useSetLayoutShortcut", () => {
  function renderSetShortcut(config: UserConfig | null): {
    store: ReturnType<typeof createStore>;
    setShortcut: (layoutId: string, chord: string | null) => Promise<void>;
  } {
    const store = createStore();
    store.set(userConfigAtom, config);
    const { result } = renderHook(() => useSetLayoutShortcut(), { wrapper: wrapperFor(store) });
    return { store, setShortcut: result.current };
  }

  it("writes a chord under the layout's binding id, preserving other bindings", async () => {
    const { store, setShortcut } = renderSetShortcut(withKeybindings({ [layoutShortcutBindingId("b")]: "Alt+2" }));

    await act(async () => {
      await setShortcut("a", "Alt+1");
    });

    expect(store.get(userConfigAtom)?.keybindings).toEqual({
      [layoutShortcutBindingId("b")]: "Alt+2",
      [layoutShortcutBindingId("a")]: "Alt+1",
    });
  });

  it("clearing with null removes the key entirely rather than storing a null entry", async () => {
    const { store, setShortcut } = renderSetShortcut(withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));

    await act(async () => {
      await setShortcut("a", null);
    });

    const keybindings = store.get(userConfigAtom)?.keybindings ?? {};
    expect(layoutShortcutBindingId("a") in keybindings).toBe(false);
    expect(keybindings).toEqual({});
  });

  it("clearing a never-set shortcut performs no write and leaves the config untouched", async () => {
    const config = withKeybindings({ [layoutShortcutBindingId("b")]: "Alt+2" });
    const { store, setShortcut } = renderSetShortcut(config);

    await act(async () => {
      await setShortcut("a", null);
    });

    expect(mockUpdateUserConfig).not.toHaveBeenCalled();
    // No optimistic write means the atom still holds the exact seeded object.
    expect(store.get(userConfigAtom)).toBe(config);
  });
});

describe("useLayoutBindingConflict", () => {
  function renderConflict(
    config: UserConfig | null,
    layouts: ReadonlyArray<SavedLayout>,
  ): (chord: string, selfBindingId: string) => NamedBinding | null {
    const store = createStore();
    store.set(userConfigAtom, config);
    store.set(savedLayoutsAtom, layouts);
    const { result } = renderHook(() => useLayoutBindingConflict(), { wrapper: wrapperFor(store) });
    return result.current;
  }

  it("detects a conflict with a static built-in binding", () => {
    const findConflict = renderConflict(null, []);
    // command_palette defaults to Meta+K.
    expect(findConflict("Meta+K", layoutShortcutBindingId("a"))?.id).toBe("command_palette");
  });

  it("detects a conflict with another layout's dynamic binding", () => {
    const findConflict = renderConflict(withKeybindings({ [layoutShortcutBindingId("b")]: "Alt+2" }), [
      makeLayout("a"),
      makeLayout("b"),
    ]);
    expect(findConflict("Alt+2", layoutShortcutBindingId("a"))?.id).toBe(layoutShortcutBindingId("b"));
  });

  it("ignores the layout's own current binding", () => {
    const findConflict = renderConflict(withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }), [
      makeLayout("a"),
    ]);
    // Re-recording the same chord onto the same layout is not a conflict.
    expect(findConflict("Alt+1", layoutShortcutBindingId("a"))).toBeNull();
  });

  it("returns null for a free chord and skips unbound entries", () => {
    const findConflict = renderConflict(null, [makeLayout("a"), makeLayout("b")]);
    // Layouts a, b and every System layout are unbound (null binding); a chord no
    // one holds must match none of them without tripping on the null entries.
    expect(findConflict("Alt+9", layoutShortcutBindingId("a"))).toBeNull();
  });

  it("matches chords that are spelled differently but parse equal", () => {
    const findConflict = renderConflict(withKeybindings({ [layoutShortcutBindingId("b")]: "Option+Shift+2" }), [
      makeLayout("a"),
      makeLayout("b"),
    ]);
    // "Option" parses to the same modifier as "Alt" and modifier order is
    // irrelevant, so the differently-spelled query still collides.
    expect(findConflict("Shift+Alt+2", layoutShortcutBindingId("a"))?.id).toBe(layoutShortcutBindingId("b"));
  });
});
