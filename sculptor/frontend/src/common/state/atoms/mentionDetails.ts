import type { Atom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { CodingAgentTaskView, Project, TaskStatus, Workspace } from "../../../api";
import { agentAtomFamily, agentsArrayAtom, agentStatusAtomFamily } from "./agents";
import { projectAtomFamily } from "./projects";
import { workspaceAtomFamily, workspacesArrayAtom } from "./workspaces";

// Maximum agent / workspace titles surfaced by the detail pane. Keeps the
// hover-card compact and bounds the work done on every arrow-key tick
// when the picker's side pane subscribes to one of these atoms.
const DETAIL_PANE_PREVIEW_LIMIT = 3;

export type AgentDetail = {
  agent: CodingAgentTaskView;
  status: TaskStatus | undefined;
  workspace: Workspace | null;
};

export type WorkspaceDetail = {
  workspace: Workspace;
  project: Project | null;
  agents: ReadonlyArray<CodingAgentTaskView>;
  agentCount: number;
};

export type RepositoryDetail = {
  project: Project;
  workspaces: ReadonlyArray<Workspace>;
  workspaceCount: number;
};

/**
 * Composite detail for an agent chip's hover card and the entity picker's
 * right-hand pane. Returns ``null`` when the agent atom has no entry for
 * ``agentId`` (deleted or unknown) so consumers can render the deleted-state
 * fallback uniformly.
 */
export const agentDetailAtomFamily = atomFamily<string, Atom<AgentDetail | null>>((agentId) =>
  atom<AgentDetail | null>((get) => {
    const agent = get(agentAtomFamily(agentId));
    if (agent === null) return null;
    return {
      agent,
      status: get(agentStatusAtomFamily(agentId)),
      // Agent may not yet be associated with a workspace (Phase 1 implicit
      // 1:1 creation hasn't finished, or the link was cleared). Fall back
      // to null so the detail pane can skip the workspace-description row.
      workspace: agent.workspaceId === null ? null : get(workspaceAtomFamily(agent.workspaceId)),
    };
  }),
);

/**
 * Composite detail for a workspace chip. ``agents`` is the list of
 * non-deleted agents attached to this workspace, capped at
 * ``DETAIL_PANE_PREVIEW_LIMIT``; ``agentCount`` is the full count so the UI
 * can show "+N more" affordances.
 */
export const workspaceDetailAtomFamily = atomFamily<string, Atom<WorkspaceDetail | null>>((workspaceId) =>
  atom<WorkspaceDetail | null>((get) => {
    const workspace = get(workspaceAtomFamily(workspaceId));
    if (workspace === null) return null;
    const allAgents = get(agentsArrayAtom) ?? [];
    const agents = allAgents.filter((agent) => agent.workspaceId === workspaceId);
    return {
      workspace,
      project: get(projectAtomFamily(workspace.projectId)),
      agents: agents.slice(0, DETAIL_PANE_PREVIEW_LIMIT),
      agentCount: agents.length,
    };
  }),
);

/**
 * Composite detail for a repository (project) chip. ``workspaces`` lists the
 * first ``DETAIL_PANE_PREVIEW_LIMIT`` non-deleted workspaces whose
 * ``projectId`` matches; ``workspaceCount`` is the full count.
 */
export const repositoryDetailAtomFamily = atomFamily<string, Atom<RepositoryDetail | null>>((projectId) =>
  atom<RepositoryDetail | null>((get) => {
    const project = get(projectAtomFamily(projectId));
    if (project === null) return null;
    const allWorkspaces = get(workspacesArrayAtom) ?? [];
    const workspaces = allWorkspaces.filter((ws) => ws.projectId === projectId);
    return {
      project,
      workspaces: workspaces.slice(0, DETAIL_PANE_PREVIEW_LIMIT),
      workspaceCount: workspaces.length,
    };
  }),
);
