import { Check, Circle, CircleAlert } from "lucide-react";
import type { ReactElement, ReactNode } from "react";

import type { WorkflowAgentProgress, WorkflowPhaseProgress, WorkflowTaskState } from "~/api";
import { isGenericToolContent } from "~/common/Guards.ts";
import { useCurrentTaskWorkflowStates } from "~/common/state/hooks/useTaskDetail";

import headerStyles from "./PopoverHeader.module.scss";
import { defaultPopoverShell, type ToolEntryProps } from "./toolEntryShell.tsx";
import styles from "./WorkflowEntry.module.scss";
import { formatTokenCount, formatWorkflowDuration } from "./workflowFormat.ts";

// Agent rows rendered per phase before collapsing the rest into a summary
// row. Workflows can run up to 1000 agents; the popover scrolls but
// rendering them all would still be wasteful.
const MAX_AGENT_ROWS_PER_PHASE = 50;

const STATUS_WORDS: Record<string, string> = {
  running: "Running…",
  completed: "Completed",
  failed: "Failed",
  stopped: "Stopped",
};

type WorkflowProgressEntry = WorkflowPhaseProgress | WorkflowAgentProgress;

const isPhaseEntry = (entry: WorkflowProgressEntry): entry is WorkflowPhaseProgress =>
  entry.objectType === "WorkflowPhaseProgress";

const isAgentEntry = (entry: WorkflowProgressEntry): entry is WorkflowAgentProgress =>
  entry.objectType === "WorkflowAgentProgress";

type WorkflowEntryData = {
  phases: Array<WorkflowPhaseProgress>;
  agentsByPhaseIndex: Map<number | null, Array<WorkflowAgentProgress>>;
};

const groupEntriesByPhase = (state: WorkflowTaskState): WorkflowEntryData => {
  // The backend dedupes the wire's event-log-shaped tree, but persisted or
  // older payloads may still repeat an entry index — keep the last
  // occurrence so an agent renders once with its current state.
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
  const agentsByPhaseIndex = new Map<number | null, Array<WorkflowAgentProgress>>();
  for (const agent of agentByIndex.values()) {
    const key = agent.phaseIndex ?? null;
    const agents = agentsByPhaseIndex.get(key) ?? [];
    agents.push(agent);
    agentsByPhaseIndex.set(key, agents);
  }
  return { phases, agentsByPhaseIndex };
};

const AgentStatusIcon = ({ agent }: { agent: WorkflowAgentProgress }): ReactElement => {
  if (agent.state === "done") {
    return <Check className={styles.statusIconDone} aria-label="done" />;
  }

  if (agent.state === "error") {
    return <CircleAlert className={styles.statusIconError} aria-label="error" />;
  }
  // "start" means the agent was created but may still be waiting for a
  // concurrency slot; it counts as queued until a start time appears. Any
  // progress means it's actively running.
  const isQueued = agent.state === "start" && (agent.startedAt === undefined || agent.startedAt === null);
  if (isQueued) {
    return <Circle className={styles.statusIconQueued} aria-label="queued" />;
  }
  return <span className={styles.statusDotRunning} aria-label="running" />;
};

const AgentRow = ({ agent }: { agent: WorkflowAgentProgress }): ReactElement => {
  const metaParts: Array<string> = [];
  if (agent.tokens !== undefined && agent.tokens !== null) metaParts.push(formatTokenCount(agent.tokens));
  if (agent.durationMs !== undefined && agent.durationMs !== null) {
    metaParts.push(formatWorkflowDuration(agent.durationMs));
  }

  // Secondary line: the error when failed, the result preview when done,
  // otherwise the latest tool activity while running.
  const secondaryText =
    agent.state === "error" ? agent.error : agent.state === "done" ? agent.resultPreview : agent.lastToolSummary;

  return (
    <div className={styles.agentRow} data-agent-state={agent.state}>
      <span className={styles.agentStatus}>
        <AgentStatusIcon agent={agent} />
      </span>
      <div className={styles.agentMain}>
        <div className={styles.agentHeadline}>
          <span className={styles.agentLabel} title={agent.promptPreview || undefined}>
            {agent.label || `agent ${agent.index}`}
          </span>
          {agent.cached === true && <span className={styles.cachedBadge}>cached</span>}
          {agent.model && <span className={styles.agentModel}>{agent.model}</span>}
          {metaParts.length > 0 && <span className={styles.agentMeta}>{metaParts.join(" · ")}</span>}
        </div>
        {secondaryText && (
          <div className={agent.state === "error" ? styles.agentSecondaryError : styles.agentSecondary}>
            {secondaryText}
          </div>
        )}
      </div>
    </div>
  );
};

const AgentList = ({ agents }: { agents: Array<WorkflowAgentProgress> }): ReactElement => {
  const visibleAgents = agents.slice(0, MAX_AGENT_ROWS_PER_PHASE);
  const hiddenAgents = agents.slice(MAX_AGENT_ROWS_PER_PHASE);
  const hiddenRunningCount = hiddenAgents.filter((a) => a.state === "start" || a.state === "progress").length;
  const hiddenDoneCount = hiddenAgents.filter((a) => a.state === "done").length;

  return (
    <>
      {visibleAgents.map((agent) => (
        <AgentRow key={agent.index} agent={agent} />
      ))}
      {hiddenAgents.length > 0 && (
        <div className={styles.moreRow}>
          +{hiddenAgents.length} more ({hiddenRunningCount} running, {hiddenDoneCount} done)
        </div>
      )}
    </>
  );
};

const WorkflowProgressBody = ({ state }: { state: WorkflowTaskState }): ReactElement => {
  const { phases, agentsByPhaseIndex } = groupEntriesByPhase(state);
  const knownPhaseIndexes = new Set(phases.map((phase) => phase.index));
  // Agents whose phaseIndex doesn't match any phase entry (or is unset) still
  // render, in an untitled trailing section.
  const orphanAgents = Array.from(agentsByPhaseIndex.entries())
    .filter(([phaseIndex]) => phaseIndex === null || !knownPhaseIndexes.has(phaseIndex))
    .flatMap(([, agents]) => agents);

  const hasAnyAgents = (state.entries ?? []).some(isAgentEntry);
  if (!hasAnyAgents) {
    return (
      <div className={styles.emptyBody}>{state.status === "running" ? "Starting workflow…" : "No agents ran."}</div>
    );
  }

  return (
    <div className={styles.body}>
      {phases.map((phase) => {
        const agents = agentsByPhaseIndex.get(phase.index) ?? [];
        if (agents.length === 0) return null;
        return (
          <div key={phase.index} className={styles.section}>
            <div className={styles.sectionLabel}>{phase.title || `Phase ${phase.index + 1}`}</div>
            <AgentList agents={agents} />
          </div>
        );
      })}
      {orphanAgents.length > 0 && (
        <div className={styles.section}>
          <AgentList agents={orphanAgents} />
        </div>
      )}
    </div>
  );
};

const getWorkflowDisplayName = (inputs: {
  state: WorkflowTaskState | undefined;
  block: ToolEntryProps["block"];
}): string => {
  if (inputs.state?.workflowName) return inputs.state.workflowName;
  const name = inputs.block?.input?.name;
  if (typeof name === "string" && name) return name;
  const scriptPath = inputs.block?.input?.scriptPath;
  if (typeof scriptPath === "string" && scriptPath) return scriptPath;
  return "workflow";
};

const buildUsageMeta = (state: WorkflowTaskState): ReactNode => {
  const parts: Array<string> = [];
  const usage = state.usage;
  if (usage?.totalTokens !== undefined && usage?.totalTokens !== null) {
    parts.push(`${formatTokenCount(usage.totalTokens)} tokens`);
  }

  if (usage?.toolUses !== undefined && usage?.toolUses !== null) {
    parts.push(`${usage.toolUses} ${usage.toolUses === 1 ? "tool" : "tools"}`);
  }

  if (usage?.durationMs !== undefined && usage?.durationMs !== null) {
    parts.push(formatWorkflowDuration(usage.durationMs));
  }
  return parts.length > 0 ? parts.join(" · ") : undefined;
};

export const WorkflowEntry = ({ block, result, renderShell = defaultPopoverShell }: ToolEntryProps): ReactElement => {
  const workflowStates = useCurrentTaskWorkflowStates();
  const toolUseId = block?.id ?? result?.toolUseId ?? "";
  const state = workflowStates[toolUseId];

  const displayName = getWorkflowDisplayName({ state, block });

  if (!state) {
    // No live/replayed workflow state (e.g. the run's notification was lost).
    // Fall back to the launch acknowledgement text from the tool result.
    const launchText = result && isGenericToolContent(result.content) ? result.content.text : "";
    return renderShell({
      title: <span className={headerStyles.titleCode}>{displayName}</span>,
      bodyText: launchText,
    });
  }

  const statusWord = STATUS_WORDS[state.status ?? ""] ?? state.status;
  return renderShell({
    title: (
      <span className={styles.title}>
        <span className={headerStyles.titleCode}>{displayName}</span>
        <span className={state.status === "failed" ? styles.statusWordError : styles.statusWord}>{statusWord}</span>
      </span>
    ),
    meta: buildUsageMeta(state),
    bodyText: "",
    body: <WorkflowProgressBody state={state} />,
  });
};
