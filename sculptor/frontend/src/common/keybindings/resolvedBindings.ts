import { atom } from "jotai";

import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";

import { KEYBINDING_DEFINITIONS } from "./definitions.ts";
import type { KeybindingId, ResolvedKeybinding } from "./model.ts";

export const keybindingsAtom = atom<ReadonlyArray<ResolvedKeybinding>>((get) => {
  const userConfig = get(userConfigAtom);
  const overrides: Record<string, string | null> = userConfig?.keybindings ?? {};

  return KEYBINDING_DEFINITIONS.map((def) => {
    const hasOverride = def.id in overrides;
    return {
      ...def,
      binding: hasOverride ? overrides[def.id] || null : def.defaultBinding,
      isDefault: !hasOverride,
    };
  });
});

export const keybindingsMapAtom = atom<Record<KeybindingId, ResolvedKeybinding>>((get) => {
  const bindings = get(keybindingsAtom);
  const map = {} as Record<KeybindingId, ResolvedKeybinding>;
  for (const binding of bindings) {
    map[binding.id] = binding;
  }
  return map;
});
