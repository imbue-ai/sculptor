import { createElement } from "react";

import { describeLayout } from "~/components/layouts/layoutSummary.ts";
import { LayoutWireframeIcon } from "~/components/layouts/LayoutWireframeIcon.tsx";
import { orderLayoutsByMru } from "~/components/layouts/switcherOrder.ts";
import { applyLayoutAtom } from "~/components/sections/layoutActions.ts";
import type { SavedLayout } from "~/components/sections/persistence/types.ts";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { appliedLayoutIdAtom, layoutMruAtom, resolvedLayoutsAtom } from "~/components/sections/savedLayoutAtoms.ts";
import type { PanelId } from "~/components/sections/sectionTypes.ts";
import { SYSTEM_DEFAULT_LAYOUT_ID, SYSTEM_DEFAULT_LAYOUT_SUMMARY } from "~/components/sections/systemDefaultLayout.ts";

import type { CommandRuntime } from "../runtime.ts";
import type { Command, CommandIcon, DynamicProvider } from "../types.ts";

/**
 * One "Switch to <layout>" command per saved layout (MRU-ordered), applying the
 * layout to the current workspace directly from Cmd+K. Scoped to workspace routes.
 * The subtitle marks the current layout and otherwise summarizes its panels.
 *
 * Any atom read here MUST be listed in `dynamicProviderInputsAtom` (hooks.ts) so
 * the palette recomputes when layouts / MRU / the applied pointer change while open.
 */
export const buildLayoutsProvider = (runtime: CommandRuntime): DynamicProvider => {
  // Cache the per-layout wireframe icon by id so the same component identity is
  // reused across produce() calls (a fresh icon each time would re-render rows).
  const iconCache = new Map<string, CommandIcon>();
  const iconFor = (layout: SavedLayout): CommandIcon => {
    const cached = iconCache.get(layout.id);
    if (cached !== undefined) {
      return cached;
    }
    const icon: CommandIcon = ({ size }: { size?: number }) =>
      createElement(LayoutWireframeIcon, { captured: layout.captured, size });
    iconCache.set(layout.id, icon);
    return icon;
  };

  return {
    id: "dynamic.layouts",
    produce: (ctx): Array<Command> => {
      if (!ctx.route.isWorkspace) {
        return [];
      }
      const layouts = runtime.store.get(resolvedLayoutsAtom);
      const mru = runtime.store.get(layoutMruAtom);
      const appliedLayoutId = runtime.store.get(appliedLayoutIdAtom);
      const registry = runtime.store.get(panelRegistryAtom);
      const nameOf = (id: PanelId): string => registry.find((definition) => definition.id === id)?.displayName ?? id;

      return orderLayoutsByMru(layouts, mru).map((layout, index): Command => {
        const summary =
          layout.id === SYSTEM_DEFAULT_LAYOUT_ID
            ? SYSTEM_DEFAULT_LAYOUT_SUMMARY
            : describeLayout(layout.captured, nameOf);
        return {
          id: `layouts.switch.${layout.id}`,
          title: `Switch to ${layout.name}`,
          subtitle: layout.id === appliedLayoutId ? "Current layout" : summary,
          keywords: ["layout", "switch", "apply", layout.name.toLowerCase()],
          group: "layouts",
          icon: iconFor(layout),
          order: index,
          perform: (): void => {
            // Re-resolve by id at run time in case the layout list changed.
            const current = runtime.store.get(resolvedLayoutsAtom).find((candidate) => candidate.id === layout.id);
            if (current !== undefined) {
              runtime.store.set(applyLayoutAtom, current);
            }
          },
        };
      });
    },
  };
};
