// Agent-panel placement for the workspace shell: the two write atoms through which
// agent panels enter the layout and become visible.
//
//   - ensureAgentPanelsPlacedAtom — the additive reconcile: every agent task of the
//     active workspace owns a center tab. Safe to run on every task tick.
//   - activateAgentPanelAtom — the navigation activation: the routed agent's panel
//     becomes its sub-section's active panel (placed into center on first sight).
//
// The reconcile is purely ADDITIVE and idempotent: it appends missing agent:<taskId>
// panels to the center section and never removes a panel, changes the active panel,
// or moves the active sub-section — an agent that appears WITHOUT a navigation (a
// CI-babysitter the backend spawns, an agent created from another surface) gains a
// tab without stealing focus from whatever the user is viewing. It never prunes
// either: a placed panel whose task is gone is removed by the agent close/delete
// flow, not here.
//
// Activation, by contrast, deliberately moves focus, so its caller must key it off
// actual navigations (the route's task id) — never off layout state, because
// switching tabs writes activePanel without navigating and would be snapped right
// back (see useWorkspaceShellBootstrap).

import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";

import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { shallowArrayEqual } from "~/common/utils/shallowArrayEqual.ts";
import { workspaceLayoutAtom } from "~/pages/workspace/layout/atoms/section.ts";
import { openPanelAtom, setActivePanelAtom } from "~/pages/workspace/layout/atoms/sectionActions.ts";
import type { WorkspaceLayoutState } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { makeAgentPanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";
import type { PanelId, SubSectionId } from "~/pages/workspace/layout/types/section.ts";

// New agent panels land in the center section's primary sub-section, mirroring the
// manual create path (useAddPanelActions defaults its target sub-section to center).
const AGENT_CENTER_SUB_SECTION: SubSectionId = "center";

// The agent task ids of one workspace — the reconcile's input. tasksArrayAtom
// rebuilds its array on EVERY per-task update (a streaming token tick included), so
// subscribers of this slice re-render only when the workspace's agent id list
// actually changes — an agent created or deleted — not on every tick.
export const workspaceAgentIdsAtomFamily = atomFamily((workspaceId: string) =>
  selectAtom(
    tasksArrayAtom,
    (tasks): ReadonlyArray<string> =>
      (tasks ?? []).filter((task) => task.workspaceId === workspaceId).map((task) => task.id),
    shallowArrayEqual,
  ),
);

// The same per-workspace slice, but preserving tasksArrayAtom's `undefined`
// "first task snapshot hasn't arrived" state. Consumers that must tell an
// agentless workspace apart from tasks-still-loading (e.g. the workspace
// page's agentless render gate) read this one; the reconcile input above
// coalesces to [] because placing zero panels is a no-op either way.
export const workspaceAgentIdsWhenLoadedAtomFamily = atomFamily((workspaceId: string) =>
  selectAtom(
    tasksArrayAtom,
    (tasks): ReadonlyArray<string> | undefined =>
      tasks === undefined ? undefined : tasks.filter((task) => task.workspaceId === workspaceId).map((task) => task.id),
    (a, b) => (a === undefined || b === undefined ? a === b : shallowArrayEqual(a, b)),
  ),
);

// Pure reducer behind ensureAgentPanelsPlacedAtom: place every given agent task's
// panel, appending the missing ones to the center section. Returns the input
// snapshot (same reference) when nothing needs to change, so the caller can skip
// the write (and the persist/notify cycle) on the every-task-tick invocations.
//
// Idempotent and duplicate-proof by construction: a panel is "missing" only while
// it has no placement, and the center order is rebuilt so each panel id appears at
// most once — a newly placed id is filtered out of the existing entries before it
// is appended, and entries duplicated in a persisted snapshot are collapsed to
// their first occurrence. A duplicate order entry would render as a duplicate tab,
// so the invariant is repaired here rather than trusted.
export const withAgentPanelsEnsured = (
  layout: WorkspaceLayoutState,
  agentTaskIds: ReadonlyArray<string>,
): WorkspaceLayoutState => {
  const missing: Array<PanelId> = [];
  const missingSet = new Set<PanelId>();
  for (const taskId of agentTaskIds) {
    const panelId = makeAgentPanelId(taskId);
    if (layout.placement[panelId] === undefined && !missingSet.has(panelId)) {
      missing.push(panelId);
      missingSet.add(panelId);
    }
  }

  const existingOrder = layout.order[AGENT_CENTER_SUB_SECTION] ?? [];
  const kept = new Set<PanelId>();
  const dedupedExisting = existingOrder.filter((panelId) => {
    if (kept.has(panelId) || missingSet.has(panelId)) {
      return false;
    }
    kept.add(panelId);
    return true;
  });
  const nextOrder = [...dedupedExisting, ...missing];

  const isOrderUnchanged =
    nextOrder.length === existingOrder.length && nextOrder.every((panelId, index) => panelId === existingOrder[index]);
  if (missing.length === 0 && isOrderUnchanged) {
    return layout;
  }

  const placement = { ...layout.placement };
  for (const panelId of missing) {
    placement[panelId] = AGENT_CENTER_SUB_SECTION;
  }
  return { ...layout, placement, order: { ...layout.order, [AGENT_CENTER_SUB_SECTION]: nextOrder } };
};

// Ensure each of the given agent task ids has its panel placed (open) in the center
// section. Writes once with the full reconciled snapshot, and skips the write
// entirely when nothing is missing so it never spins the layout's persist/notify
// cycle on every task tick.
export const ensureAgentPanelsPlacedAtom = atom(null, (get, set, agentTaskIds: ReadonlyArray<string>) => {
  const layout = get(workspaceLayoutAtom);
  const next = withAgentPanelsEnsured(layout, agentTaskIds);
  if (next !== layout) {
    set(workspaceLayoutAtom, next);
  }
});

// Make the agent's panel the visible one: a panel that has never been placed opens
// in the center (openPanelAtom activates it and expands the section as part of
// opening); an already-placed panel is activated in whatever sub-section it lives
// in — activation never MOVES a panel out of a section the user put it in. Both
// branches go through the layout reducers, which keep the order duplicate-free.
export const activateAgentPanelAtom = atom(null, (get, set, taskId: string) => {
  const panelId = makeAgentPanelId(taskId);
  const placement = get(workspaceLayoutAtom).placement[panelId];
  if (placement === undefined) {
    set(openPanelAtom, { panelId, in: AGENT_CENTER_SUB_SECTION });
  } else {
    set(setActivePanelAtom, { panelId, in: placement });
  }
});
