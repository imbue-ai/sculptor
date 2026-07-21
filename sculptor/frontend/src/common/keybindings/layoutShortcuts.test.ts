import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { UserConfig } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import type { SavedLayout } from "~/components/sections/persistence/types.ts";
import { SAVED_LAYOUT_VERSION } from "~/components/sections/persistence/types.ts";
import { savedLayoutsAtom } from "~/components/sections/savedLayoutAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID } from "~/components/sections/systemDefaultLayout.ts";

import {
  allNamedBindingsAtom,
  dynamicLayoutKeybindingsAtom,
  layoutShortcutBindingId,
  layoutShortcutBindingsAtom,
} from "./layoutShortcuts.ts";

function makeLayout(id: string): SavedLayout {
  return { id, name: id, version: SAVED_LAYOUT_VERSION, captured: SYSTEM_DEFAULT_LAYOUT.captured };
}

function withKeybindings(bindings: Record<string, string | null>): UserConfig {
  return { keybindings: bindings } as unknown as UserConfig;
}

beforeEach(() => {
  localStorage.clear();
});

describe("layout shortcuts", () => {
  it("resolves a per-layout binding from userConfig.keybindings, System Default included", () => {
    const store = createStore();
    store.set(savedLayoutsAtom, [makeLayout("a"), makeLayout("b")]);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));

    const dynamic = store.get(dynamicLayoutKeybindingsAtom);
    const rowA = dynamic.find((kb) => kb.layoutId === "a");
    expect(rowA?.binding).toBe("Alt+1");
    expect(rowA?.name).toBe("Apply “a” layout");
    expect(dynamic.find((kb) => kb.layoutId === "b")?.binding).toBeNull();
    expect(dynamic.some((kb) => kb.layoutId === SYSTEM_DEFAULT_LAYOUT_ID)).toBe(true);
  });

  it("maps only bound layouts in layoutShortcutBindingsAtom", () => {
    const store = createStore();
    store.set(savedLayoutsAtom, [makeLayout("a"), makeLayout("b")]);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));
    expect(store.get(layoutShortcutBindingsAtom)).toEqual({ a: "Alt+1" });
  });

  it("includes both static and per-layout bindings in allNamedBindingsAtom", () => {
    const store = createStore();
    store.set(savedLayoutsAtom, [makeLayout("a")]);
    store.set(userConfigAtom, withKeybindings({ [layoutShortcutBindingId("a")]: "Alt+1" }));
    const all = store.get(allNamedBindingsAtom);
    expect(all.some((b) => b.id === "command_palette")).toBe(true);
    expect(all.some((b) => b.id === layoutShortcutBindingId("a") && b.binding === "Alt+1")).toBe(true);
  });
});
