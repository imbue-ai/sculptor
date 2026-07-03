import type { WorkflowAgentProgress, WorkflowPhaseProgress, WorkflowTaskState } from "~/api";

type WorkflowProgressEntry = WorkflowPhaseProgress | WorkflowAgentProgress;

const isPhaseEntry = (entry: WorkflowProgressEntry): entry is WorkflowPhaseProgress =>
  entry.objectType === "WorkflowPhaseProgress";

const isAgentEntry = (entry: WorkflowProgressEntry): entry is WorkflowAgentProgress =>
  entry.objectType === "WorkflowAgentProgress";

export const isAgentDone = (agent: WorkflowAgentProgress): boolean => agent.state === "done" || agent.state === "error";

export type WorkflowEntryGroups = {
  /** Phases sorted by index. */
  phases: Array<WorkflowPhaseProgress>;
  /** Agents grouped by phaseIndex; null collects agents with no known phase. */
  agentsByPhaseIndex: Map<number | null, Array<WorkflowAgentProgress>>;
};

/**
 * Group a workflow's entries into sorted phases and per-phase agent lists.
 *
 * The backend dedupes the wire's event-log-shaped tree, but persisted or
 * older payloads may still repeat an entry index — keep the last occurrence
 * so an agent renders once with its current state. Agents whose phaseIndex
 * doesn't match any phase entry are grouped under null.
 */
export const groupWorkflowEntriesByPhase = (state: WorkflowTaskState): WorkflowEntryGroups => {
  const phaseByIndex = new Map<number, WorkflowPhaseProgress>();
  const agentByIndex = new Map<number, WorkflowAgentProgress>();
  for (const entry of state.entries ?? []) {
    if (isPhaseEntry(entry)) {
      phaseByIndex.set(entry.index, entry);
    } else if (isAgentEntry(entry)) {
      agentByIndex.set(entry.index, entry);
    }
  }

  const phases = Array.from(phaseByIndex.values()).sort((a, b) => a.index - b.index);
  const knownPhaseIndexes = new Set(phases.map((phase) => phase.index));
  const agentsByPhaseIndex = new Map<number | null, Array<WorkflowAgentProgress>>();
  for (const agent of agentByIndex.values()) {
    const phaseIndex = agent.phaseIndex ?? null;
    const key = phaseIndex !== null && knownPhaseIndexes.has(phaseIndex) ? phaseIndex : null;
    const agents = agentsByPhaseIndex.get(key) ?? [];
    agents.push(agent);
    agentsByPhaseIndex.set(key, agents);
  }

  for (const agents of agentsByPhaseIndex.values()) {
    agents.sort((a, b) => a.index - b.index);
  }
  return { phases, agentsByPhaseIndex };
};

export const getWorkflowDisplayName = (inputs: {
  state: WorkflowTaskState | undefined;
  input: { [key: string]: unknown } | undefined;
}): string => {
  if (inputs.state?.workflowName) return inputs.state.workflowName;
  const name = inputs.input?.name;
  if (typeof name === "string" && name) return name;
  const scriptPath = inputs.input?.scriptPath;
  if (typeof scriptPath === "string" && scriptPath) return scriptPath;
  return "workflow";
};

export type WorkflowAgentCounts = {
  doneCount: number;
  totalCount: number;
  /** Title of the first phase that still has unfinished agents; "" when none. */
  activePhaseTitle: string;
};

export const countWorkflowAgents = (state: WorkflowTaskState): WorkflowAgentCounts => {
  const { phases, agentsByPhaseIndex } = groupWorkflowEntriesByPhase(state);
  let doneCount = 0;
  let totalCount = 0;
  for (const agents of agentsByPhaseIndex.values()) {
    totalCount += agents.length;
    doneCount += agents.filter(isAgentDone).length;
  }
  const activePhase = phases.find((phase) => {
    const agents = agentsByPhaseIndex.get(phase.index) ?? [];
    return agents.some((agent) => !isAgentDone(agent));
  });
  return { doneCount, totalCount, activePhaseTitle: activePhase?.title ?? "" };
};
