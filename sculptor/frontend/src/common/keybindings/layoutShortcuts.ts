// Per-layout keyboard shortcuts. Unlike the static keybindings (a fixed registry
// keyed by the closed KeybindingId union), these are DYNAMIC: one binding per saved
// Layout, and Layouts come and go. Rather than widen KeybindingId, a layout binding
// is stored in `userConfig.keybindings` under a namespaced string key
// (`layout.apply.<layoutId>`) — the same arbitrary Record the static overrides use,
// so it needs no backend/wire change — and surfaced here as its own resolved-binding
// lane the Settings UI, the runtime dispatcher, and conflict detection read from.

import type { Atom } from "jotai";
import { atom } from "jotai";

import { resolvedLayoutsAtom } from "~/components/sections/savedLayoutAtoms.ts";

import { userConfigAtom } from "../state/atoms/userConfig.ts";
import { keybindingsAtom } from "./atoms.ts";

// Namespaced userConfig.keybindings key for a Layout's "apply" shortcut. Mirrors the
// `layouts.switch.<id>` command-palette id convention.
const LAYOUT_SHORTCUT_PREFIX = "layout.apply.";

export function layoutShortcutBindingId(layoutId: string): string {
  return `${LAYOUT_SHORTCUT_PREFIX}${layoutId}`;
}

export function isLayoutShortcutBindingId(id: string): boolean {
  return id.startsWith(LAYOUT_SHORTCUT_PREFIX);
}

export function layoutIdFromShortcutBindingId(id: string): string | null {
  return isLayoutShortcutBindingId(id) ? id.slice(LAYOUT_SHORTCUT_PREFIX.length) : null;
}

// A resolved per-layout binding, shaped like the static ResolvedKeybinding the
// settings rows render, but with a string id and the synthetic "layouts" category
// (deliberately NOT a member of the static KeybindingCategory union — the static
// keybinding types stay untouched).
export type LayoutKeybinding = {
  id: string;
  layoutId: string;
  name: string;
  description: string;
  category: "layouts";
  binding: string | null;
  isDefault: boolean;
};

// One resolved binding per selectable Layout (System Default included), in
// resolvedLayoutsAtom order. Drives the Settings ▸ Keybindings "Layouts" group.
export const dynamicLayoutKeybindingsAtom: Atom<ReadonlyArray<LayoutKeybinding>> = atom((get) => {
  const overrides: Record<string, string | null> = get(userConfigAtom)?.keybindings ?? {};
  return get(resolvedLayoutsAtom).map((layout) => {
    const binding = overrides[layoutShortcutBindingId(layout.id)] || null;
    return {
      id: layoutShortcutBindingId(layout.id),
      layoutId: layout.id,
      name: `Apply “${layout.name}” layout`,
      description: `Switch this workspace to the ${layout.name} layout`,
      category: "layouts" as const,
      binding,
      isDefault: binding === null,
    };
  });
});

// layoutId → assigned chord, for every Layout that has one. Used for the switcher
// row hint and by the runtime dispatcher; unbound Layouts are omitted.
export const layoutShortcutBindingsAtom: Atom<Readonly<Record<string, string>>> = atom((get) => {
  const overrides: Record<string, string | null> = get(userConfigAtom)?.keybindings ?? {};
  const result: Record<string, string> = {};
  for (const layout of get(resolvedLayoutsAtom)) {
    const binding = overrides[layoutShortcutBindingId(layout.id)];
    if (typeof binding === "string" && binding !== "") {
      result[layout.id] = binding;
    }
  }
  return result;
});

// The minimal binding shape conflict detection needs, across BOTH the static
// registry and the dynamic per-layout bindings — so a chord recorded in either lane
// is checked against the other (a per-layout chord can't silently shadow a static
// binding, and vice versa).
export type NamedBinding = { id: string; name: string; binding: string | null };

export const allNamedBindingsAtom: Atom<ReadonlyArray<NamedBinding>> = atom((get) => {
  const staticBindings: ReadonlyArray<NamedBinding> = get(keybindingsAtom).map((kb) => ({
    id: kb.id,
    name: kb.name,
    binding: kb.binding,
  }));
  const layoutBindings: ReadonlyArray<NamedBinding> = get(dynamicLayoutKeybindingsAtom).map((kb) => ({
    id: kb.id,
    name: kb.name,
    binding: kb.binding,
  }));
  return [...staticBindings, ...layoutBindings];
});
