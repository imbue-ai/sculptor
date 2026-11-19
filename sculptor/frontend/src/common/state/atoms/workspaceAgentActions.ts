// Workspace-scoped agent resolution + actions for panels that act on "the
// workspace's current agent" without living inside a chat panel (e.g. the
// Changes panel's commit button, Notes "add to prompt", the Skills gate). The
// Commit and Create PR actions also gather their own message here, so every
// entry point sends the same text and is enabled by the same rule.
//
// These deliberately do NOT go through `chatActionsAtom`: its closures are
// registered by a mounted chat panel and nulled on unmount, so any control
// routed through it goes dead the moment no chat is the active tab (the
// Changes panel as the active center tab unmounts the chat). They also do NOT
// read the route: activating a different center tab doesn't navigate, so the
// route's agent id goes stale. The section layout is the live source of which
// agents the workspace is showing.

import type { Getter, Setter } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { LlmModel } from "~/api";
import { postAgentTerminalInput, sendWorkspaceAgentMessages, TaskStatus } from "~/api";
import { agentDetailStateAtomFamily } from "~/common/state/atoms/agentDetails.ts";
import {
  agentAcceptsAutomatedPromptsAtomFamily,
  agentAtomFamily,
  agentModelAtomFamily,
  agentsArrayAtom,
  agentStatusAtomFamily,
  agentSupportsChatInterfaceAtomFamily,
} from "~/common/state/atoms/agents.ts";
import { commitPromptSendFailedToastAtom, terminalPromptRejectedToastAtom } from "~/common/state/atoms/toasts.ts";
import {
  commitPromptAtom,
  jjCommitPromptAtom,
  jjPrCreationPromptAtom,
  prCreationPromptAtom,
} from "~/common/state/atoms/userConfig.ts";
import { workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState.ts";
import {
  agentIdForWorkspaceAtomFamily,
  asLiveWorkspace,
  workspaceAtomFamily,
} from "~/common/state/atoms/workspaces.ts";
import { workspaceTargetBranchesAtomFamily } from "~/common/state/atoms/workspaceTargetBranches.ts";
import {
  type AgentPromptKind,
  buildCommitMessage,
  buildCreatePrMessage,
  type PromptWorkspace,
} from "~/common/utils/agentPrompts.ts";
import { DEFAULT_LLM_MODEL } from "~/common/utils/modelConstants.ts";
import { workspaceVcsOf } from "~/common/utils/workspaceVcs.ts";
import { workspaceLayoutFamily } from "~/pages/workspace/layout/atoms/section.ts";
import type { WorkspaceLayoutState } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { AGENT_PANEL_ID_PREFIX, makeAgentPanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";
import type { SubSectionId } from "~/pages/workspace/layout/types/section.ts";
import { toSecondary } from "~/pages/workspace/layout/types/section.ts";

// Where to look for agent panels first. Center is the primary chat surface;
// the side/bottom sections host chats the user has deliberately moved there.
const SUB_SECTION_PREFERENCE: ReadonlyArray<SubSectionId> = (["center", "right", "left", "bottom"] as const).flatMap(
  (section): Array<SubSectionId> => [section, toSecondary(section)],
);

const agentIdFromPanelId = (panelId: string): string | undefined =>
  panelId.startsWith(AGENT_PANEL_ID_PREFIX) ? panelId.slice(AGENT_PANEL_ID_PREFIX.length) : undefined;

// Open agent-panel agent ids in a sub-section, in tab order (any placed but
// unordered panel is appended so no open panel is dropped).
const agentIdsIn = (layout: WorkspaceLayoutState, subSection: SubSectionId): Array<string> => {
  const placed = Object.keys(layout.placement).filter((panelId) => layout.placement[panelId] === subSection);
  const placedSet = new Set(placed);
  const ordered = (layout.order[subSection] ?? []).filter((panelId) => placedSet.has(panelId));
  const orderedSet = new Set(ordered);
  return [...ordered, ...placed.filter((panelId) => !orderedSet.has(panelId))]
    .map(agentIdFromPanelId)
    .filter((agentId): agentId is string => agentId !== undefined);
};

// Whether the agent's panel is the active tab of the sub-section it lives in,
// i.e. the agent is actually on screen.
const isAgentTabVisible = (layout: WorkspaceLayoutState, agentId: string): boolean => {
  const panelId = makeAgentPanelId(agentId);
  const subSection = layout.placement[panelId];
  return subSection !== undefined && layout.activePanel[subSection] === panelId;
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
    (get, set, agentId: string) => {
      const baseAtom = lastFocusedChatAgentBaseAtomFamily(workspaceId);
      if (get(baseAtom) !== agentId) {
        set(baseAtom, agentId);
      }
    },
  ),
);

/**
 * The workspace's "current chat agent": the agent whose chat composer a
 * chat-targeted feature (Notes "add to prompt", the Skills gate) should
 * address. Resolution order:
 *
 *   1. the chat panel the user most recently interacted with, while it is
 *      still open (with several chats visible at once, actions follow the
 *      user's focus rather than the section ranking below),
 *   2. an agent panel that is its sub-section's active tab (a visible chat),
 *   3. any open agent panel, in tab order,
 *   4. the workspace's first chat-capable agent (layout not seeded yet).
 *
 * Terminal-harness agents (`supports_chat_interface` false) are skipped —
 * they have no chat composer, so composer-draft writes aimed at them would
 * land nowhere; a chat hidden behind a terminal tab still receives them.
 * `undefined` when the workspace has no chat-capable agent (loaded) at all.
 *
 * Automated-prompt features (Commit, Create PR) must NOT use this: they can
 * target prompt-capable terminal agents too — see `activeAgentIdAtomFamily`.
 */
export const activeChatAgentIdAtomFamily = atomFamily((workspaceId: string) =>
  atom<string | undefined>((get) => {
    // A candidate must have loaded agent data (a stale layout can reference a
    // deleted agent) and must not be a terminal-only harness.
    const isValidTarget = (agentId: string): boolean =>
      get(agentAtomFamily(agentId)) !== null && get(agentSupportsChatInterfaceAtomFamily(agentId)) !== false;

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
      const agentId = agentIdFromPanelId(activePanelId);
      if (agentId !== undefined && isValidTarget(agentId)) return agentId;
    }

    for (const subSection of SUB_SECTION_PREFERENCE) {
      for (const agentId of agentIdsIn(layout, subSection)) {
        if (isValidTarget(agentId)) return agentId;
      }
    }
    return get(agentsArrayAtom)?.find((agent) => agent.workspaceId === workspaceId && isValidTarget(agent.id))?.id;
  }),
);

/**
 * The workspace's "current agent": the agent an automated-prompt action
 * (commit prompt, create-PR prompt) should target. Unlike
 * `activeChatAgentIdAtomFamily`, a visible terminal agent IS the current
 * agent — prompt-capable terminals receive these prompts as terminal input
 * (see `promptRouteFor`). Resolution order:
 *
 *   1. the chat panel the user most recently interacted with, while it is
 *      still its sub-section's active tab — once the user activates another
 *      agent tab over it, that tab is the current agent,
 *   2. the first sub-section (preference order) whose active tab is an agent
 *      panel: that visible agent is authoritative, whatever its harness.
 *      A prompt-incapable terminal here resolves (and
 *      `canPromptActiveAgentAtomFamily` disables the action) rather than
 *      falling through — sending the prompt to a chat hidden behind the
 *      terminal the user is looking at would be invisible and surprising,
 *   3. no agent is visible (e.g. a static panel is the active tab
 *      everywhere): any open chat-capable agent panel, in tab order — chat
 *      messages queue and surface when the chat is re-shown, whereas typing
 *      into a hidden terminal's PTY would not be seen,
 *   4. no agent panel is open: the agent the workspace's route last showed,
 *      whatever its harness — the mobile shell renders that agent without
 *      seeding the panel layout,
 *   5. the workspace's first chat-capable agent (layout not seeded yet).
 *
 * `undefined` when nothing resolves; candidates must have loaded agent data
 * (a stale layout can reference a deleted agent).
 */
export const activeAgentIdAtomFamily = atomFamily((workspaceId: string) =>
  atom<string | undefined>((get) => {
    const isLoaded = (agentId: string): boolean => get(agentAtomFamily(agentId)) !== null;
    const isHiddenFallbackTarget = (agentId: string): boolean =>
      isLoaded(agentId) && get(agentSupportsChatInterfaceAtomFamily(agentId)) !== false;

    const layout = get(workspaceLayoutFamily(workspaceId));

    const lastFocused = get(lastFocusedChatAgentAtomFamily(workspaceId));
    if (lastFocused !== undefined && isAgentTabVisible(layout, lastFocused) && isLoaded(lastFocused)) {
      return lastFocused;
    }

    for (const subSection of SUB_SECTION_PREFERENCE) {
      const activePanelId = layout.activePanel[subSection];
      if (activePanelId === undefined || layout.placement[activePanelId] !== subSection) continue;
      const agentId = agentIdFromPanelId(activePanelId);
      if (agentId !== undefined && isLoaded(agentId)) return agentId;
    }

    for (const subSection of SUB_SECTION_PREFERENCE) {
      for (const agentId of agentIdsIn(layout, subSection)) {
        if (isHiddenFallbackTarget(agentId)) return agentId;
      }
    }

    const lastViewed = get(agentIdForWorkspaceAtomFamily(workspaceId));
    if (lastViewed !== null && isLoaded(lastViewed)) return lastViewed;

    return get(agentsArrayAtom)?.find((agent) => agent.workspaceId === workspaceId && isHiddenFallbackTarget(agent.id))
      ?.id;
  }),
);

// How a workspace-scoped automated prompt reaches the agent, if it can at all:
// chat-capable agents take chat messages; terminal agents take PTY input, but
// only when their registration opted in via `accepts_automated_prompts` —
// plain terminals and non-opt-in registrations take nothing (`undefined`).
// `supports_chat_interface` defaults to the chat route while capabilities are
// still loading, mirroring the chat resolver's `!== false` check.
const promptRouteFor = (get: Getter, agentId: string): "chat" | "terminal" | undefined => {
  if (get(agentSupportsChatInterfaceAtomFamily(agentId)) !== false) return "chat";
  return get(agentAcceptsAutomatedPromptsAtomFamily(agentId)) === true ? "terminal" : undefined;
};

/**
 * Whether the workspace's current agent can take an automated prompt right
 * now: a target agent resolves and can accept the prompt. Controls that send
 * one disable themselves while this is false. Chat agents must have no queued
 * messages (mirrors the chat input, which disables sends while a message is
 * queued so queue promotion stays unambiguous); prompt-capable terminal agents
 * must be at their prompt (READY/WAITING, mirroring `useTerminalChatActions`).
 */
export const canPromptActiveAgentAtomFamily = atomFamily((workspaceId: string) =>
  atom<boolean>((get) => {
    const agentId = get(activeAgentIdAtomFamily(workspaceId));
    if (agentId === undefined) return false;
    const route = promptRouteFor(get, agentId);
    if (route === undefined) return false;
    if (route === "terminal") {
      const status = get(agentStatusAtomFamily(agentId));
      return status === TaskStatus.READY || status === TaskStatus.WAITING;
    }
    return (get(agentDetailStateAtomFamily(agentId))?.queuedChatMessages.length ?? 0) === 0;
  }),
);

// Send an automated prompt to the workspace's current agent. Chat agents get a
// chat message via the send API directly, so the prompt lands while no chat
// panel is mounted; prompt-capable terminal agents get the prompt typed and
// submitted through the terminal-input endpoint. `sendFailedTitle` heads the
// toast shown when the chat-route send fails.
const sendAutomatedPrompt = async (
  get: Getter,
  set: Setter,
  inputs: { workspaceId: string; message: string; sendFailedTitle: string },
): Promise<void> => {
  const { workspaceId, message, sendFailedTitle } = inputs;
  const agentId = get(activeAgentIdAtomFamily(workspaceId));
  if (agentId === undefined) return;
  const route = promptRouteFor(get, agentId);
  if (route === undefined) return;
  if (route === "terminal") {
    try {
      await postAgentTerminalInput({ path: { agent_id: agentId }, body: { text: message, submit: true } });
    } catch {
      // The endpoint's authoritative guard fired: the program went busy (or
      // its hooks are silent) between the click and the write. Surface it;
      // do not retry (mirrors `useTerminalChatActions`).
      set(terminalPromptRejectedToastAtom, {
        title: "Agent is busy",
        description: "Try again when it's at its prompt.",
      });
    }
    return;
  }
  const model = get(agentModelAtomFamily(agentId));
  try {
    await sendWorkspaceAgentMessages({
      path: { workspace_id: workspaceId, agent_id: agentId },
      body: { message, model: (model as LlmModel) || DEFAULT_LLM_MODEL },
    });
  } catch {
    // The send failed (network/HTTP). Callers fire the action without
    // awaiting it, so surface the failure here or it is silently dropped as an
    // unhandled rejection with no user feedback.
    set(commitPromptSendFailedToastAtom, {
      title: sendFailedTitle,
      description: "Check your connection and try again.",
    });
  }
};

// What the Commit and Create PR messages say about the workspace: its version
// control, its target, and for jj its bookmark. Undefined until the workspace
// is loaded and, for a jj workspace, until its jj state arrives, since the
// message names the bookmark the state reports.
const readMessageWorkspace = (get: Getter, workspaceId: string): PromptWorkspace | undefined => {
  const workspace = asLiveWorkspace(get(workspaceAtomFamily(workspaceId)));
  if (workspace === null) return undefined;
  const targetBranch = workspace.targetBranch || null;
  switch (workspaceVcsOf(workspace)) {
    case "git":
      return { vcs: "git", targetBranch };
    case "jj": {
      const jjState = get(workspaceJjStateAtomFamily(workspaceId));
      if (jjState === null) return undefined;
      const prBaseNames = get(workspaceTargetBranchesAtomFamily(workspaceId))?.prBaseNames ?? {};
      return {
        vcs: "jj",
        bookmark:
          jjState.primaryBookmark === null
            ? { status: "missing", requestedName: workspace.requestedBranchName || null }
            : { status: "set", name: jjState.primaryBookmark },
        target:
          targetBranch === null ? null : { bookmark: targetBranch, prBaseName: prBaseNames[targetBranch] ?? null },
      };
    }
  }
};

/**
 * Which setting a workspace's Commit or Create PR prompt comes from: a git
 * workspace's git prompt; a jj workspace's jj prompt, or, while no jj prompt is
 * set, the git prompt in its place.
 */
export type AgentPromptSource = "git" | "jj" | "git-for-jj";

const PROMPT_SETTINGS = {
  commit: { gitPrompt: commitPromptAtom, jjPrompt: jjCommitPromptAtom },
  "pr-creation": { gitPrompt: prCreationPromptAtom, jjPrompt: jjPrCreationPromptAtom },
} as const satisfies Record<AgentPromptKind, unknown>;

// The prompt a workspace's message starts from and the setting it came from;
// undefined until the workspace is loaded.
const choosePrompt = (
  get: Getter,
  workspaceId: string,
  kind: AgentPromptKind,
): { source: AgentPromptSource; prompt: string } | undefined => {
  const workspace = asLiveWorkspace(get(workspaceAtomFamily(workspaceId)));
  if (workspace === null) return undefined;
  const settings = PROMPT_SETTINGS[kind];
  switch (workspaceVcsOf(workspace)) {
    case "git":
      return { source: "git", prompt: get(settings.gitPrompt) };
    case "jj": {
      const jjPrompt = get(settings.jjPrompt);
      return jjPrompt === null
        ? { source: "git-for-jj", prompt: get(settings.gitPrompt) }
        : { source: "jj", prompt: jjPrompt };
    }
  }
};

/** Which setting the workspace's commit prompt comes from; undefined until the workspace is loaded. */
export const commitPromptSourceAtomFamily = atomFamily((workspaceId: string) =>
  atom<AgentPromptSource | undefined>((get) => choosePrompt(get, workspaceId, "commit")?.source),
);

/** Which setting the workspace's PR creation prompt comes from; undefined until the workspace is loaded. */
export const prCreationPromptSourceAtomFamily = atomFamily((workspaceId: string) =>
  atom<AgentPromptSource | undefined>((get) => choosePrompt(get, workspaceId, "pr-creation")?.source),
);

/** The message Commit sends to the workspace's current agent; undefined until its inputs are known. */
export const commitMessageAtomFamily = atomFamily((workspaceId: string) =>
  atom<string | undefined>((get) => {
    const workspace = readMessageWorkspace(get, workspaceId);
    const chosen = choosePrompt(get, workspaceId, "commit");
    if (workspace === undefined || chosen === undefined) return undefined;
    return buildCommitMessage({ prompt: chosen.prompt, workspace });
  }),
);

/** The message Create PR sends to the workspace's current agent; undefined until its inputs are known. */
export const createPrMessageAtomFamily = atomFamily((workspaceId: string) =>
  atom<string | undefined>((get) => {
    const workspace = readMessageWorkspace(get, workspaceId);
    const chosen = choosePrompt(get, workspaceId, "pr-creation");
    if (workspace === undefined || chosen === undefined) return undefined;
    return buildCreatePrMessage({ prompt: chosen.prompt, workspace });
  }),
);

/** Whether Commit can be sent now. Every Commit entry point is enabled by this rule. */
export const canCommitAtomFamily = atomFamily((workspaceId: string) =>
  atom<boolean>(
    (get) =>
      get(canPromptActiveAgentAtomFamily(workspaceId)) && get(commitMessageAtomFamily(workspaceId)) !== undefined,
  ),
);

/**
 * Whether Create PR can be sent now: as Commit, and the workspace has a target
 * to open the pull request into. Every Create PR entry point is enabled by this rule.
 */
export const canCreatePrAtomFamily = atomFamily((workspaceId: string) =>
  atom<boolean>(
    (get) =>
      get(canPromptActiveAgentAtomFamily(workspaceId)) &&
      get(createPrMessageAtomFamily(workspaceId)) !== undefined &&
      Boolean(asLiveWorkspace(get(workspaceAtomFamily(workspaceId)))?.targetBranch),
  ),
);

/** Send the commit message to the workspace's current agent. */
export const commitActionAtomFamily = atomFamily((workspaceId: string) =>
  atom(null, async (get, set): Promise<void> => {
    const message = get(commitMessageAtomFamily(workspaceId));
    if (message === undefined) return;
    await sendAutomatedPrompt(get, set, { workspaceId, message, sendFailedTitle: "Couldn't send commit request" });
  }),
);

/** Send the create-pull-request message to the workspace's current agent. */
export const createPrActionAtomFamily = atomFamily((workspaceId: string) =>
  atom(null, async (get, set): Promise<void> => {
    const message = get(createPrMessageAtomFamily(workspaceId));
    if (message === undefined) return;
    await sendAutomatedPrompt(get, set, { workspaceId, message, sendFailedTitle: "Couldn't send pull request prompt" });
  }),
);

/**
 * Drop a workspace's cached agent-resolution/action atoms when it is deleted.
 * The atomFamily entries are keyed by workspace id and memoized for the session,
 * so without this they linger for every deleted workspace. The derived families
 * recompute on next access; this only frees their memoized entries plus the
 * transient last-focused-chat state. Called alongside the layout cleanup.
 */
export const removeWorkspaceAgentActionState = (workspaceId: string): void => {
  lastFocusedChatAgentBaseAtomFamily.remove(workspaceId);
  lastFocusedChatAgentAtomFamily.remove(workspaceId);
  activeChatAgentIdAtomFamily.remove(workspaceId);
  activeAgentIdAtomFamily.remove(workspaceId);
  canPromptActiveAgentAtomFamily.remove(workspaceId);
  commitPromptSourceAtomFamily.remove(workspaceId);
  prCreationPromptSourceAtomFamily.remove(workspaceId);
  commitMessageAtomFamily.remove(workspaceId);
  createPrMessageAtomFamily.remove(workspaceId);
  canCommitAtomFamily.remove(workspaceId);
  canCreatePrAtomFamily.remove(workspaceId);
  commitActionAtomFamily.remove(workspaceId);
  createPrActionAtomFamily.remove(workspaceId);
};
