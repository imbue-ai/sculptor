import { createStore } from "jotai";
import { Circle } from "lucide-react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";

import type { UserConfig } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { panelRegistryAtom } from "~/components/panels/atoms.ts";
import type { PanelDefinition } from "~/components/panels/types.ts";

import { keybindingsAtom, keybindingsMapAtom } from "./atoms.ts";

const TEST_PANEL: PanelDefinition = {
  id: "files",
  displayName: "Files",
  description: "Browse repo files and diffs",
  icon: Circle,
  defaultZone: "top-left",
  defaultShortcut: "",
  component: () => createElement("div"),
};

const makeConfig = (keybindings: Record<string, string | null>): UserConfig =>
  ({ keybindings }) as unknown as UserConfig;

describe("keybindingsAtom panel entries", () => {
  it("emits a panel_<id> entry for each registered panel", () => {
    const store = createStore();
    store.set(panelRegistryAtom, [TEST_PANEL]);

    const bindings = store.get(keybindingsAtom);
    const entry = bindings.find((b) => b.id === "panel_files");
    expect(entry).toBeDefined();
    expect(entry!.category).toBe("panels");
    expect(entry!.name).toBe("Files");
    expect(entry!.description).toBe("Browse repo files and diffs");
    expect(entry!.binding).toBeNull();
    expect(entry!.defaultBinding).toBeNull();
    expect(entry!.isDefault).toBe(true);
  });

  it("applies a userConfig override to the panel binding", () => {
    const store = createStore();
    store.set(panelRegistryAtom, [TEST_PANEL]);
    store.set(userConfigAtom, { keybindings: { panel_files: "Meta+E" } } as unknown as UserConfig);

    const entry = store.get(keybindingsAtom).find((b) => b.id === "panel_files");
    expect(entry!.binding).toBe("Meta+E");
    expect(entry!.isDefault).toBe(false);
  });

  it("treats an explicit null override as not-default", () => {
    const store = createStore();
    store.set(panelRegistryAtom, [{ ...TEST_PANEL, defaultShortcut: "Meta+1" }]);
    store.set(userConfigAtom, { keybindings: { panel_files: null } } as unknown as UserConfig);

    const entry = store.get(keybindingsAtom).find((b) => b.id === "panel_files");
    expect(entry!.binding).toBeNull();
    expect(entry!.isDefault).toBe(false);
  });
});

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
});
