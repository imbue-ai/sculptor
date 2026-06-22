import { panelRegistryAtom } from "~/components/panels/atoms.ts";
import type { PanelDefinition } from "~/components/panels/types.ts";

import type { CommandRuntime } from "../runtime.ts";
import type { Command, DynamicProvider } from "../types.ts";

/**
 * Surfaces one Cmd+K command per registered IDE panel — Files,
 * Actions, Agent tasks, Terminal, Notes (if the feature flag is on),
 * and any future panel that gets added to `workspacePanels` /
 * `panelRegistryAtom`. Each command toggles that panel's visibility via
 * `usePanelActions().togglePanel`, which handles open / switch-active /
 * close-zone correctly even when several panels share a zone.
 *
 * Driving these off the registry (instead of hardcoding a static list)
 * means a new panel only needs an entry in `workspacePanels` to
 * appear in the palette — no cross-cutting changes to this file or the
 * builtin command list.
 *
 * Visibility:
 *   - Scoped to the `view.panels` sub-page so the root list isn't
 *     dominated by N "Toggle X" rows. The user opens the page via
 *     "Toggle panel visibility..." (see builtinCommands/panels.ts).
 *   - The palette closes after each toggle rather than using
 *     `keepOpen: true`. Mounting a heavy panel (e.g. the file browser)
 *     while the palette is still on screen makes the toggle feel
 *     noticeably laggier than toggling via the topbar button. Closing
 *     first lets the panel mount alone, matching the mouse-toggle latency.
 *
 * Ranking:
 *   - `boost` lifts these rows above same-tier Settings sub-page entries
 *     that share their name. Without it, typing "Actions" surfaces
 *     "Settings: Actions" (exact title match, score 1000 → 250 after
 *     the page-scoped penalty) above "Toggle Actions" (word-prefix
 *     match, 200 → 50 after penalty). The boost reverses that so the
 *     panel toggle leads. Settings entries still appear, just below.
 */

// Ad-hoc keyword extensions per panel id. The display name "File browser"
// already matches "browser" and "file browser" via the title; the alias
// here adds "files" (so the legacy short name still resolves) and
// "explorer" (the VS Code shorthand).
const PANEL_SEARCH_ALIASES: Record<string, ReadonlyArray<string>> = {
  files: ["files", "explorer"],
};

// 8× lifts a penalised word-prefix match (200 × 0.25 = 50) to 400,
// clearing the penalised exact-title match of a same-name Settings
// entry (1000 × 0.25 = 250). Tiers stay intact: a penalised
// subsequence (≤ 0.5) still cannot reach a real word-prefix match
// even after the boost.
const PANEL_TOGGLE_BOOST = 8;

export const buildPanelTogglesProvider = (runtime: CommandRuntime): DynamicProvider => ({
  id: "dynamic.panel_toggles",
  produce: (ctx): Array<Command> => {
    if (!ctx.route.isWorkspace) return [];
    const registry = runtime.store.get(panelRegistryAtom) ?? [];
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
        perform: () => runtime.ui.togglePanel(panel.id),
      };
    });
  },
});
