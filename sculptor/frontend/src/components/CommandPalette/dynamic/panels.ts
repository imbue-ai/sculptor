import { workspaceLayoutAtom } from "~/pages/workspace/layout/atoms/section.ts";
import { jumpToSectionAtom, openPanelAtom } from "~/pages/workspace/layout/atoms/sectionActions.ts";
import type { PanelDefinition } from "~/pages/workspace/layout/registry/panelRegistry.ts";
import { panelRegistryAtom } from "~/pages/workspace/layout/registry/panelRegistry.ts";

import type { CommandRuntime } from "../runtime.ts";
import type { Command, DynamicProvider } from "../types.ts";

/**
 * Surfaces one Cmd+K command per placed section panel — Files, Actions, agents,
 * terminals, Notes, and any future panel — driven off the new section
 * `panelRegistryAtom`. Each command REVEALS its panel: it activates the panel in
 * its section, expands the section if collapsed, and jumps there. "Show X" is
 * jump-only — it never closes the panel, even when the panel is already visible
 * and active (running it then is simply a jump to its section).
 *
 * Driving these off the registry (instead of hardcoding a static list) means a new
 * panel only needs an entry in the registry to appear in the palette.
 *
 * Visibility:
 *   - Scoped to the `view.panels` sub-page so the root list isn't dominated by N
 *     "Show X" rows. The user opens the page via the panels entry point (see
 *     builtinCommands/panels.ts).
 *   - The palette closes after each reveal rather than using `keepOpen: true`.
 *     Mounting a heavy panel (e.g. the file browser) while the palette is still on
 *     screen makes the reveal feel noticeably laggier; closing first lets the panel
 *     mount alone, matching the mouse latency.
 *
 * Ranking:
 *   - `boost` lifts these rows above same-tier Settings sub-page entries that share
 *     their name. Without it, typing "Actions" surfaces "Settings: Actions" above
 *     "Show Actions". The boost reverses that so the panel reveal leads.
 */

// Ad-hoc keyword extensions per panel id. The display name "Files" already matches
// "files"; the alias here adds "explorer" (the VS Code shorthand).
const PANEL_SEARCH_ALIASES: Record<string, ReadonlyArray<string>> = {
  files: ["files", "explorer"],
};

// 8× lifts a penalised word-prefix match (200 × 0.25 = 50) to 400, clearing the
// penalised exact-title match of a same-name Settings entry (1000 × 0.25 = 250).
const PANEL_TOGGLE_BOOST = 8;

export const buildPanelTogglesProvider = (runtime: CommandRuntime): DynamicProvider => ({
  id: "dynamic.panel_toggles",
  produce: (ctx): Array<Command> => {
    if (!ctx.route.isWorkspace) return [];
    const registry = runtime.store.get(panelRegistryAtom);
    // Only panels actively placed in a section — this list focuses/reveals an existing
    // panel, it does not open new ones (that is what "Add panel..." is for).
    const placement = runtime.store.get(workspaceLayoutAtom).placement;
    return registry
      .filter((panel: PanelDefinition) => placement[panel.id] !== undefined)
      .map((panel: PanelDefinition): Command => {
        const aliases = PANEL_SEARCH_ALIASES[panel.id] ?? [];
        return {
          id: `view.toggle_panel.${panel.id}`,
          title: `Show ${panel.displayName}`,
          subtitle: "Focus this panel",
          keywords: ["panel", "show", "focus", "reveal", panel.id, panel.displayName.toLowerCase(), ...aliases],
          group: "panels",
          icon: panel.icon,
          onPage: "view.panels",
          boost: PANEL_TOGGLE_BOOST,
          perform: (): void => {
            // Re-read placement at run time — the panel may have moved (or closed)
            // since this command list was produced.
            const current = runtime.store.get(workspaceLayoutAtom).placement[panel.id];
            if (current === undefined) {
              return;
            }
            // openPanel activates the panel in place and expands a collapsed host
            // section; the jump makes the section active and pulses the ring.
            runtime.store.set(openPanelAtom, { panelId: panel.id, in: current });
            runtime.store.set(jumpToSectionAtom, { subSection: current });
          },
        };
      });
  },
});
