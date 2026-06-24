import type { PanelDefinition } from "~/components/sections/registry/panelRegistry.ts";
import { panelRegistryAtom } from "~/components/sections/registry/panelRegistry.ts";
import { togglePanelAtom } from "~/components/sections/sectionActions.ts";
import type { SubSectionId } from "~/components/sections/sectionTypes.ts";

import type { CommandRuntime } from "../runtime.ts";
import type { Command, DynamicProvider } from "../types.ts";

/**
 * Surfaces one Cmd+K command per registered section panel — Files, Actions, agents,
 * terminals, Notes, and any future panel — driven off the new section
 * `panelRegistryAtom`. Each command smart-toggles that panel's visibility via
 * `togglePanelAtom`, which opens / activates / collapses the panel in its section.
 *
 * Driving these off the registry (instead of hardcoding a static list) means a new
 * panel only needs an entry in the registry to appear in the palette.
 *
 * Visibility:
 *   - Scoped to the `view.panels` sub-page so the root list isn't dominated by N
 *     "Toggle X" rows. The user opens the page via "Toggle panel visibility..." (see
 *     builtinCommands/panels.ts).
 *   - The palette closes after each toggle rather than using `keepOpen: true`.
 *     Mounting a heavy panel (e.g. the file browser) while the palette is still on
 *     screen makes the toggle feel noticeably laggier; closing first lets the panel
 *     mount alone, matching the mouse-toggle latency.
 *
 * Ranking:
 *   - `boost` lifts these rows above same-tier Settings sub-page entries that share
 *     their name. Without it, typing "Actions" surfaces "Settings: Actions" above
 *     "Toggle Actions". The boost reverses that so the panel toggle leads.
 */

// Ad-hoc keyword extensions per panel id. The display name "Files" already matches
// "files"; the alias here adds "explorer" (the VS Code shorthand).
const PANEL_SEARCH_ALIASES: Record<string, ReadonlyArray<string>> = {
  files: ["files", "explorer"],
};

// 8× lifts a penalised word-prefix match (200 × 0.25 = 50) to 400, clearing the
// penalised exact-title match of a same-name Settings entry (1000 × 0.25 = 250).
const PANEL_TOGGLE_BOOST = 8;

// Where a panel lands when toggled on for the first time (it has never been placed):
// its registered default section, falling back to center.
const fallbackSectionFor = (panel: PanelDefinition): SubSectionId => panel.defaultSection ?? "center";

export const buildPanelTogglesProvider = (runtime: CommandRuntime): DynamicProvider => ({
  id: "dynamic.panel_toggles",
  produce: (ctx): Array<Command> => {
    if (!ctx.route.isWorkspace) return [];
    const registry = runtime.store.get(panelRegistryAtom);
    return registry.map((panel: PanelDefinition): Command => {
      const aliases = PANEL_SEARCH_ALIASES[panel.id] ?? [];
      return {
        id: `view.toggle_panel.${panel.id}`,
        title: `Toggle ${panel.displayName}`,
        subtitle: "Show or hide this panel",
        keywords: ["panel", "show", "hide", panel.id, panel.displayName.toLowerCase(), ...aliases],
        group: "view",
        icon: panel.icon,
        onPage: "view.panels",
        boost: PANEL_TOGGLE_BOOST,
        perform: () =>
          runtime.store.set(togglePanelAtom, { panelId: panel.id, fallbackSection: fallbackSectionFor(panel) }),
      };
    });
  },
});
