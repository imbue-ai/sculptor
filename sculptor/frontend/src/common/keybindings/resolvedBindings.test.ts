import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { UserConfig } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";

import { keybindingsMapAtom } from "./resolvedBindings.ts";

const makeConfig = (keybindings: Record<string, string | null>): UserConfig =>
  ({ keybindings }) as unknown as UserConfig;

describe("keybindings resolution", () => {
  it("falls back to the default binding when no override exists", () => {
    const store = createStore();
    store.set(userConfigAtom, makeConfig({}));
    const map = store.get(keybindingsMapAtom);
    expect(map.command_palette.binding).toBe("Meta+K");
    expect(map.command_palette.isDefault).toBe(true);
  });

  it("respects a custom override", () => {
    const store = createStore();
    store.set(userConfigAtom, makeConfig({ command_palette: "Meta+Shift+F" }));
    const map = store.get(keybindingsMapAtom);
    expect(map.command_palette.binding).toBe("Meta+Shift+F");
    expect(map.command_palette.isDefault).toBe(false);
  });

  it("treats a cleared (null) override as unbound", () => {
    const store = createStore();
    store.set(userConfigAtom, makeConfig({ command_palette: null }));
    const map = store.get(keybindingsMapAtom);
    expect(map.command_palette.binding).toBeNull();
    expect(map.command_palette.isDefault).toBe(false);
  });

  it("does NOT inherit a legacy search_agents override (migration since removed)", () => {
    // search_agents and command_palette are not the
    // same feature, so customizations of the old binding should NOT
    // silently transfer. Users with a customized 'Search agents' fall
    // back to the new default.
    const store = createStore();
    store.set(userConfigAtom, makeConfig({ search_agents: "Meta+P" }));
    const map = store.get(keybindingsMapAtom);
    expect(map.command_palette.binding).toBe("Meta+K");
    expect(map.command_palette.isDefault).toBe(true);
  });

  it("tolerates an override saved for a removed binding id (e.g. close_workspace)", () => {
    // A user may have persisted an override for a binding that no longer exists
    // (close_workspace was removed from the definitions). Resolution must ignore
    // the unknown id — not crash, not surface a phantom binding — while every
    // still-defined binding (including one with its own override) resolves.
    const store = createStore();
    store.set(userConfigAtom, makeConfig({ close_workspace: "Meta+W", delete_workspace: "Meta+D" }));
    const map = store.get(keybindingsMapAtom);
    expect("close_workspace" in map).toBe(false);
    expect(map.delete_workspace.binding).toBe("Meta+D");
    expect(map.command_palette.binding).toBe("Meta+K");
  });
});
