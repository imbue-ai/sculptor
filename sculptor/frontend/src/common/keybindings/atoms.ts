import { atom } from "jotai";

import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { panelRegistryAtom } from "~/components/panels/atoms.ts";

import { KEYBINDING_DEFINITIONS } from "./definitions.ts";
import type { KeybindingCategory, KeybindingId, PanelKeybindingId, ResolvedKeybinding } from "./types.ts";

export const keybindingsAtom = atom<ReadonlyArray<ResolvedKeybinding>>((get) => {
  const userConfig = get(userConfigAtom);
  const overrides = (userConfig?.keybindings ?? {}) as Record<string, string | null>;
  const panels = get(panelRegistryAtom);

  const staticBindings = KEYBINDING_DEFINITIONS.map((def) => {
    const hasOverride = def.id in overrides;
    return {
      ...def,
      binding: hasOverride ? overrides[def.id] || null : def.defaultBinding,
      isDefault: !hasOverride,
    };
  });

  const panelBindings = panels.map((panel): ResolvedKeybinding => {
    const id: PanelKeybindingId = `panel_${panel.id}`;
    const hasOverride = id in overrides;
    const defaultBinding = panel.defaultShortcut || null;
    return {
      id,
      name: panel.displayName,
      description: panel.description,
      category: "panels" as KeybindingCategory,
      defaultBinding,
      binding: hasOverride ? overrides[id] || null : defaultBinding,
      isDefault: !hasOverride,
    };
  });

  return [...staticBindings, ...panelBindings];
});

export const keybindingsMapAtom = atom<Record<KeybindingId, ResolvedKeybinding>>((get) => {
  const bindings = get(keybindingsAtom);
  const map = {} as Record<KeybindingId, ResolvedKeybinding>;
  for (const binding of bindings) {
    map[binding.id] = binding;
  }
  return map;
});
