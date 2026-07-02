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

import { AGENT_TYPE_LABELS, lastUsedAgentTypeAtom, parseStoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import {
  createAgentAndNavigate,
  createTerminalInLocation,
  listAvailableLocations,
  listAvailableStaticPanels,
  openStaticPanelInLocation,
} from "~/components/sections/addPanelCore.ts";

import { addPanelTargetSubSectionAtom } from "../contextActions/atoms.ts";
import type { CommandRuntime } from "../runtime.ts";
import type { Command, DynamicProvider } from "../types.ts";

// The recent-agent label for the Cmd+K row. Registered terminal-agent programs label
// as a generic "agent" here (their display names need the registrations list, which
// isn't available synchronously in the provider) — the built-in types read straight
// from the stored default.
function recentAgentLabel(runtime: CommandRuntime): string {
  const stored = runtime.store.get(lastUsedAgentTypeAtom);
  const { agentType, registrationId } = parseStoredAgentType(stored);
  if (agentType === "registered" || registrationId !== undefined) {
    return "agent";
  }
  return AGENT_TYPE_LABELS[agentType];
}

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

    // Location page: one row per available section / sub-section.
    for (const location of listAvailableLocations(runtime.store)) {
      out.push({
        id: `addpanel.location.${location.subSection}`,
        title: location.label,
        subtitle: "Add a panel here",
        keywords: ["section", location.subSection, location.label.toLowerCase()],
        group: "panels",
        icon: PanelTopIcon,
        onPage: "addpanel.location",
        pageId: "addpanel.panels",
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
        title: `New ${recentAgentLabel(runtime)} agent`,
        subtitle: "Create an agent in this section",
        keywords: ["agent", "new", "claude", "create"],
        group: "panels",
        icon: MessageSquarePlus,
        onPage: "addpanel.panels",
        order: 10,
        // Shares the dropdown's create flow (createAgentAndNavigate): navigate to
        // the new agent on success, surface the shared error toast on failure.
        perform: (): Promise<void> => {
          const { agentType, registrationId } = parseStoredAgentType(runtime.store.get(lastUsedAgentTypeAtom));
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
      for (const panel of listAvailableStaticPanels(runtime.store)) {
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
