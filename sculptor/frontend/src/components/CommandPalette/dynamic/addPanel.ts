// Cmd+K "Add panel" flow: a two-step page drill-down that reuses the
// store-driven add-panel operations shared with the section `+` dropdown.
//
//   "Add panel…" (root, primary, workspace only)
//      → addpanel.location  (pick a destination section/sub-section)
//         → addpanel.panels (pick a panel for that location)
//
// The chosen location rides in addPanelTargetSubSectionAtom (set by the location
// rows, cleared on palette close). The panel page lists "New {recent} agent",
// "New terminal", and every single-instance panel not already open — all landing in
// the chosen location. Agents/terminals are never in the single-instance list (closing
// one ends it).

import { MessageSquarePlus, PanelTopIcon, SquareTerminal } from "lucide-react";

import { parseStoredAgentType, REGISTERED_AGENT_TYPE_PREFIX } from "~/common/state/atoms/agentTabs.ts";
import {
  availableLocationsAtom,
  availableStaticPanelsAtom,
  createAgentAndNavigate,
  createTerminalInLocation,
  openStaticPanelInLocation,
  recentAgentLabel,
  recentAgentTypeAtom,
} from "~/components/sections/addPanelCore.ts";

import { addPanelTargetSubSectionAtom } from "../contextActions/atoms.ts";
import type { CommandRuntime } from "../runtime.ts";
import type { Command, DynamicProvider } from "../types.ts";

// The "New {recent} agent" row title for the Cmd+K panel page. The registrations
// directory isn't available synchronously in this provider (it runs outside React),
// so a registered terminal-agent program can't resolve to its display name here — the
// row collapses to a plain "New agent" instead of doubling the word. Built-in types
// (Claude, pi) title from the stored default via the shared label helper.
const recentAgentRowTitle = (runtime: CommandRuntime): string => {
  const stored = runtime.store.get(recentAgentTypeAtom);
  if (stored.startsWith(REGISTERED_AGENT_TYPE_PREFIX)) {
    return "New agent";
  }
  return `New ${recentAgentLabel(stored, [])} agent`;
};

export const buildAddPanelProvider = (runtime: CommandRuntime): DynamicProvider => ({
  id: "dynamic.add_panel",
  produce: (ctx): Array<Command> => {
    if (!ctx.route.isWorkspace) {
      return [];
    }
    const out: Array<Command> = [];

    // Root entry-point.
    out.push({
      id: "addpanel.open",
      title: "Add panel...",
      subtitle: "Add a panel to a section",
      keywords: ["panel", "add", "open", "section", "new", "agent", "terminal"],
      group: "panels",
      icon: PanelTopIcon,
      pageId: "addpanel.location",
      primary: true,
      order: 90,
      perform: (): void => {
        // Page push handled by the runner; clear any stale location.
        runtime.store.set(addPanelTargetSubSectionAtom, null);
      },
    });

    // Location page: one row per available section / sub-section. `order: index`
    // preserves listAvailableLocations' spatial ordering (left → center → right →
    // bottom, split halves in place); without it groupCommands' alphabetical
    // tiebreak would reshuffle the destinations.
    for (const [index, location] of runtime.store.get(availableLocationsAtom).entries()) {
      out.push({
        id: `addpanel.location.${location.subSection}`,
        title: location.label,
        subtitle: "Add a panel here",
        keywords: ["section", location.subSection, location.label.toLowerCase()],
        group: "panels",
        icon: PanelTopIcon,
        onPage: "addpanel.location",
        pageId: "addpanel.panels",
        order: index,
        perform: (): void => {
          runtime.store.set(addPanelTargetSubSectionAtom, location.subSection);
        },
      });
    }

    // Panel page: the options for the chosen location.
    const target = runtime.store.get(addPanelTargetSubSectionAtom);
    if (target !== null) {
      out.push({
        id: "addpanel.panels.new_agent",
        title: recentAgentRowTitle(runtime),
        subtitle: "Create an agent in this section",
        keywords: ["agent", "new", "claude", "create"],
        group: "panels",
        icon: MessageSquarePlus,
        onPage: "addpanel.panels",
        order: 10,
        // Shares the dropdown's create flow (createAgentAndNavigate): navigate to
        // the new agent on success, surface the shared error toast on failure.
        perform: (): Promise<void> => {
          const { agentType, registrationId } = parseStoredAgentType(runtime.store.get(recentAgentTypeAtom));
          return createAgentAndNavigate(
            runtime.store,
            target,
            { agentType, registrationId, activeAgentId: ctx.activeAgentId ?? undefined },
            runtime.navigate.toAgent,
          );
        },
      });
      out.push({
        id: "addpanel.panels.new_terminal",
        title: "New terminal",
        subtitle: "Start an interactive shell",
        keywords: ["terminal", "shell", "command", "console"],
        group: "panels",
        icon: SquareTerminal,
        onPage: "addpanel.panels",
        order: 20,
        perform: (): void => {
          createTerminalInLocation(runtime.store, target);
        },
      });
      for (const panel of runtime.store.get(availableStaticPanelsAtom)) {
        const Icon = panel.icon;
        out.push({
          id: `addpanel.panels.${panel.id}`,
          title: panel.displayName,
          subtitle: "Add this panel",
          keywords: ["panel", panel.id, panel.displayName.toLowerCase()],
          group: "panels",
          icon: Icon,
          onPage: "addpanel.panels",
          order: 30,
          perform: (): void => {
            openStaticPanelInLocation(runtime.store, panel.id, target);
          },
        });
      }
    }

    return out;
  },
});
