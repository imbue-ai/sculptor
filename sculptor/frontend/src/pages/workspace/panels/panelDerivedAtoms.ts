// Workspace-side derived panel atoms.
//
// These live here (not in components/panels/atoms.ts) because they need the
// dynamic-panel helpers and task/terminal atoms from pages/workspace, and the
// core atoms module must not import back up into the workspace layer.
//
// All of them reduce broad, frequently-changing state (zone assignments, the
// streaming task list, terminal tabs) to narrow booleans, so subscribers only
// re-render when the answer actually flips — not on every upstream change.

import type { Atom } from "jotai";
import { atom } from "jotai";

import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { zoneAssignmentsAtom } from "~/components/panels/atoms.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { toSplitZone, ZONE_IDS } from "~/components/panels/types.ts";
import { agentIdFromPanelId, isAgentPanelId } from "~/pages/workspace/panels/dynamicPanels.tsx";
import { getWorkspaceTerminals, isTerminalPanelId, parseTerminalPanelId } from "~/pages/workspace/panels/terminals.ts";

// Whether more than one agent panel is placed anywhere in the layout. The
// only/active agent can't be closed, so tab strips use this to decide whether
// agent tabs show a close affordance.
export const hasMultipleAgentPanelsAtom: Atom<boolean> = atom((get) => {
  return Object.keys(get(zoneAssignmentsAtom)).filter((id) => isAgentPanelId(id)).length > 1;
});

// Whether a section's split (secondary) half still has a panel that is
// *assigned* to it but not yet rendered because its dynamic source (agent task
// / terminal) hasn't registered into the panel registry yet. On reload the
// layout (zone assignments) restores before the async task/terminal lists
// load, so a brief window exists where the half looks empty even though its
// agent is coming. The split must NOT collapse during that window or the panel
// is orphaned (it stays assigned to a zone that no longer renders). When the
// source is genuinely gone (the agent was deleted), this is false and the
// split collapses as expected.
const hasPendingSplitPanelAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((primaryZone) => [
    primaryZone,
    atom<boolean>((get) => {
      const splitZone = toSplitZone(primaryZone);
      const rawAssignedHere = (Object.entries(get(zoneAssignmentsAtom)) as ReadonlyArray<[PanelId, ZoneId]>)
        .filter(([, zone]) => zone === splitZone)
        .map(([id]) => id);
      if (rawAssignedHere.length === 0) return false;
      // Source lists haven't loaded yet — assume the assigned panels are pending.
      const tasks = get(tasksArrayAtom);
      if (tasks === undefined) return true;
      const taskIds = new Set(tasks.map((task) => task.id));
      const terminalTabs = get(terminalTabStateAtom);
      return rawAssignedHere.some((id) => {
        if (isAgentPanelId(id)) return taskIds.has(agentIdFromPanelId(id));
        if (isTerminalPanelId(id)) {
          const parsed = parseTerminalPanelId(id);
          return (
            parsed !== null &&
            getWorkspaceTerminals(terminalTabs, parsed.workspaceId).some((t) => t.index === parsed.index)
          );
        }
        return false;
      });
    }),
  ]),
);

export const hasPendingSplitPanelAtom = (primaryZone: ZoneId): Atom<boolean> => {
  return hasPendingSplitPanelAtomMap.get(primaryZone)!;
};
