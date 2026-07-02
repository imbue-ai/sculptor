// Workspace-scoped agent resolution + actions for panels that act on "the
// workspace's current agent" without living inside a chat panel (e.g. the
// Changes panel's commit button, Notes "add to prompt", the Skills gate).
//
// These deliberately do NOT go through `chatActionsAtom`: its closures are
// registered by a mounted chat panel and nulled on unmount, so any control
// routed through it goes dead the moment no chat is the active tab (the
// Changes panel as the active center tab unmounts the chat). They also do NOT
// read the route: activating a different center tab doesn't navigate, so the
// route's agent id goes stale. The section layout is the live source of which
// agents the workspace is showing.

import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import { LlmModel, sendWorkspaceAgentMessages } from "~/api";
import { taskDetailAtomFamily } from "~/common/state/atoms/taskDetails.ts";
import {
  taskAtomFamily,
  taskModelAtomFamily,
  tasksArrayAtom,
  taskSupportsChatInterfaceAtomFamily,
} from "~/common/state/atoms/tasks.ts";
import type { WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import { AGENT_PANEL_ID_PREFIX, makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { workspaceLayoutFamily } from "~/components/sections/sectionAtoms.ts";
import type { SubSectionId } from "~/components/sections/sectionTypes.ts";
import { toSecondary } from "~/components/sections/sectionTypes.ts";

// Where to look for agent panels first. Center is the primary chat surface;
// the side/bottom sections host chats the user has deliberately moved there.
const SUB_SECTION_PREFERENCE: ReadonlyArray<SubSectionId> = (["center", "right", "left", "bottom"] as const).flatMap(
  (section): Array<SubSectionId> => [section, toSecondary(section)],
);

const agentPanelTaskId = (panelId: string): string | undefined =>
  panelId.startsWith(AGENT_PANEL_ID_PREFIX) ? panelId.slice(AGENT_PANEL_ID_PREFIX.length) : undefined;

// Open agent-panel task ids in a sub-section, in tab order (any placed but
// unordered panel is appended so no open panel is dropped).
const agentTaskIdsIn = (layout: WorkspaceLayoutState, subSection: SubSectionId): Array<string> => {
  const placed = Object.keys(layout.placement).filter((panelId) => layout.placement[panelId] === subSection);
  const placedSet = new Set(placed);
  const ordered = (layout.order[subSection] ?? []).filter((panelId) => placedSet.has(panelId));
  const orderedSet = new Set(ordered);
  return [...ordered, ...placed.filter((panelId) => !orderedSet.has(panelId))]
    .map(agentPanelTaskId)
    .filter((taskId): taskId is string => taskId !== undefined);
};

// The chat agent the user last interacted with (pointer-down or focus inside
// a chat panel), per workspace. Deliberately transient — never persisted — so
// a reload starts from the layout-based resolution below. Kept separate from
// the layout atoms: focusing a chat is not a layout change and must not dirty
// the persistence adapter.
const lastFocusedChatAgentBaseAtomFamily = atomFamily((_workspaceId: string) => atom<string | undefined>(undefined));

/**
 * Read/record the workspace's most-recently-focused chat agent. The chat
 * surface records on every capture-phase pointer-down/focus, so the setter
 * bails when the value is unchanged to keep those events free of atom churn.
 */
export const lastFocusedChatAgentAtomFamily = atomFamily((workspaceId: string) =>
  atom(
    (get) => get(lastFocusedChatAgentBaseAtomFamily(workspaceId)),
    (get, set, taskId: string) => {
      const baseAtom = lastFocusedChatAgentBaseAtomFamily(workspaceId);
      if (get(baseAtom) !== taskId) {
        set(baseAtom, taskId);
      }
    },
  ),
);

/**
 * The workspace's "current chat agent": the agent a workspace-scoped action
 * (commit prompt, add-notes-to-prompt) should target. Resolution order:
 *
 *   1. the chat panel the user most recently interacted with, while it is
 *      still open (with several chats visible at once, actions follow the
 *      user's focus rather than the section ranking below),
 *   2. an agent panel that is its sub-section's active tab (a visible chat),
 *   3. any open agent panel, in tab order,
 *   4. the workspace's first chat-capable task (layout not seeded yet).
 *
 * Terminal-harness agents (`supports_chat_interface` false) are skipped —
 * they can't receive chat prompts, and keeping them out of the resolution is
 * what keeps commit-style actions disabled for terminal-only workspaces.
 * `undefined` when the workspace has no chat-capable agent (loaded) at all.
 */
export const activeChatAgentIdAtomFamily = atomFamily((workspaceId: string) =>
  atom<string | undefined>((get) => {
    // A candidate must have loaded task data (a stale layout can reference a
    // deleted agent) and must not be a terminal-only harness.
    const isValidTarget = (taskId: string): boolean =>
      get(taskAtomFamily(taskId)) !== null && get(taskSupportsChatInterfaceAtomFamily(taskId)) !== false;

    const layout = get(workspaceLayoutFamily(workspaceId));

    const lastFocused = get(lastFocusedChatAgentAtomFamily(workspaceId));
    if (
      lastFocused !== undefined &&
      layout.placement[makeAgentPanelId(lastFocused)] !== undefined &&
      isValidTarget(lastFocused)
    ) {
      return lastFocused;
    }

    for (const subSection of SUB_SECTION_PREFERENCE) {
      const activePanelId = layout.activePanel[subSection];
      if (activePanelId === undefined || layout.placement[activePanelId] !== subSection) continue;
      const taskId = agentPanelTaskId(activePanelId);
      if (taskId !== undefined && isValidTarget(taskId)) return taskId;
    }

    for (const subSection of SUB_SECTION_PREFERENCE) {
      for (const taskId of agentTaskIdsIn(layout, subSection)) {
        if (isValidTarget(taskId)) return taskId;
      }
    }
    return get(tasksArrayAtom)?.find((task) => task.workspaceId === workspaceId && isValidTarget(task.id))?.id;
  }),
);

/**
 * Whether the commit button may send right now: a target agent resolves and
 * that agent has no queued messages (mirrors the chat input, which disables
 * sends while a message is queued so queue promotion stays unambiguous).
 */
export const canCommitAtomFamily = atomFamily((workspaceId: string) =>
  atom<boolean>((get) => {
    const taskId = get(activeChatAgentIdAtomFamily(workspaceId));
    if (taskId === undefined) return false;
    return (get(taskDetailAtomFamily(taskId))?.queuedChatMessages.length ?? 0) === 0;
  }),
);

/**
 * Send the commit prompt to the workspace's current chat agent. Calls the
 * send API directly so committing works while no chat panel is mounted.
 */
export const commitActionAtomFamily = atomFamily((workspaceId: string) =>
  atom(null, async (get, _set, message: string): Promise<void> => {
    const taskId = get(activeChatAgentIdAtomFamily(workspaceId));
    if (taskId === undefined) return;
    const model = get(taskModelAtomFamily(taskId));
    await sendWorkspaceAgentMessages({
      path: { workspace_id: workspaceId, agent_id: taskId },
      body: { message, model: (model as LlmModel) || LlmModel.CLAUDE_4_OPUS_200K },
    });
  }),
);
