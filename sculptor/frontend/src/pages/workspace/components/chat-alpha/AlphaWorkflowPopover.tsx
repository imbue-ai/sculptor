import { Check, ChevronDown, ChevronRight, Circle, CircleAlert } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useMemo, useState } from "react";

import type { ToolResultBlock, WorkflowAgentProgress, WorkflowPhaseProgress, WorkflowTaskState } from "~/api";
import { ElementIds } from "~/api";
import { isGenericToolContent } from "~/common/Guards.ts";

import styles from "./AlphaWorkflowPopover.module.scss";
import headerStyles from "./PopoverHeader.module.scss";
import { PopoverHeader } from "./PopoverHeader.tsx";
import { groupWorkflowEntriesByPhase, isAgentDone } from "./workflowEntries.ts";
import { formatTokenCount, formatWorkflowDuration } from "./workflowFormat.ts";

// Agent rows rendered per phase before collapsing the rest into a summary
// row. Workflows can run up to 1000 agents; the pane scrolls but rendering
// them all would still be wasteful.
const MAX_AGENT_ROWS_PER_PHASE = 50;

// Sidebar key for agents whose phaseIndex doesn't match any phase entry.
const ORPHAN_PHASE_KEY = -1;

const STATUS_WORDS: Record<string, string> = {
  running: "Running…",
  completed: "Completed",
  failed: "Failed",
  stopped: "Stopped",
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

const PhaseStatusIcon = ({ agents }: { agents: ReadonlyArray<WorkflowAgentProgress> }): ReactElement => {
  if (agents.some((agent) => agent.state === "error")) {
    return <CircleAlert className={styles.statusIconError} aria-label="error" />;
  }

  if (agents.length > 0 && agents.every(isAgentDone)) {
    return <Check className={styles.statusIconDone} aria-label="done" />;
  }

  if (agents.some((agent) => agent.state === "progress" || agent.startedAt != null)) {
    return <span className={styles.statusDotRunning} aria-label="running" />;
  }
  return <Circle className={styles.statusIconQueued} aria-label="pending" />;
};

const activateOnEnterOrSpace = (onActivate: () => void): ((e: KeyboardEvent<HTMLDivElement>) => void) => {
  return (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onActivate();
    }
  };
};

const AgentMeta = ({ agent }: { agent: WorkflowAgentProgress }): ReactElement | undefined => {
  const parts: Array<string> = [];
  if (agent.tokens !== undefined && agent.tokens !== null) parts.push(formatTokenCount(agent.tokens));
  if (agent.durationMs !== undefined && agent.durationMs !== null) {
    parts.push(formatWorkflowDuration(agent.durationMs));
  }
  if (parts.length === 0) return undefined;
  return <span className={styles.agentMeta}>{parts.join(" · ")}</span>;
};

/**
 * One agent: a header row that toggles an expandable detail section with
 * Prompt / Activity / Outcome, mirroring the CLI's own /workflows view.
 */
const AgentRow = ({ agent }: { agent: WorkflowAgentProgress }): ReactElement => {
  const [isExpanded, setIsExpanded] = useState(false);
  const toggle = (): void => setIsExpanded((previous) => !previous);

  const recentToolSummaries = agent.recentToolSummaries ?? [];
  const totalToolCalls = agent.toolCalls ?? 0;
  const activityLabel =
    totalToolCalls > recentToolSummaries.length
      ? `Activity — last ${recentToolSummaries.length} of ${totalToolCalls} tool calls`
      : "Activity";

  const outcomeText =
    agent.state === "error" ? agent.error : agent.state === "done" ? agent.resultPreview : "Still running…";

  return (
    <div className={styles.agentBlock}>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        className={styles.agentRow}
        data-testid={ElementIds.ALPHA_CHAT_WORKFLOW_AGENT_ROW}
        data-agent-state={agent.state}
        onClick={toggle}
        onKeyDown={activateOnEnterOrSpace(toggle)}
      >
        <span className={styles.agentStatus}>
          <AgentStatusIcon agent={agent} />
        </span>
        <span className={styles.agentLabel}>{agent.label || `agent ${agent.index}`}</span>
        {agent.cached === true && <span className={styles.cachedBadge}>cached</span>}
        {agent.model && <span className={styles.agentModel}>{agent.model}</span>}
        <AgentMeta agent={agent} />
        {isExpanded ? (
          <ChevronDown className={styles.expandChevron} aria-hidden="true" />
        ) : (
          <ChevronRight className={styles.expandChevron} aria-hidden="true" />
        )}
      </div>
      {isExpanded && (
        <div className={styles.agentDetails}>
          {agent.promptPreview && (
            <div className={styles.detailSection}>
              <div className={styles.detailLabel}>Prompt</div>
              <div className={styles.detailText}>{agent.promptPreview}</div>
            </div>
          )}
          {recentToolSummaries.length > 0 && (
            <div className={styles.detailSection}>
              <div className={styles.detailLabel}>{activityLabel}</div>
              {recentToolSummaries.map((summary, index) => (
                // Key on the call's absolute position in the run, not its
                // slot in the rolling window — entries shift positions as
                // the window slides.
                <div key={totalToolCalls - recentToolSummaries.length + index} className={styles.detailCode}>
                  {summary}
                </div>
              ))}
            </div>
          )}
          {outcomeText && (
            <div className={styles.detailSection}>
              <div className={styles.detailLabel}>Outcome</div>
              <div className={agent.state === "error" ? styles.detailTextError : styles.detailText}>{outcomeText}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const AgentList = ({ agents }: { agents: ReadonlyArray<WorkflowAgentProgress> }): ReactElement => {
  const visibleAgents = agents.slice(0, MAX_AGENT_ROWS_PER_PHASE);
  const hiddenAgents = agents.slice(MAX_AGENT_ROWS_PER_PHASE);
  const hiddenDoneCount = hiddenAgents.filter(isAgentDone).length;

  return (
    <>
      {visibleAgents.map((agent) => (
        <AgentRow key={agent.index} agent={agent} />
      ))}
      {hiddenAgents.length > 0 && (
        <div className={styles.moreRow}>
          +{hiddenAgents.length} more ({hiddenDoneCount} done)
        </div>
      )}
    </>
  );
};

type SidebarItem = {
  key: number;
  title: string;
  agents: ReadonlyArray<WorkflowAgentProgress>;
};

const buildSidebarItems = (
  phases: ReadonlyArray<WorkflowPhaseProgress>,
  agentsByPhaseIndex: ReadonlyMap<number | null, ReadonlyArray<WorkflowAgentProgress>>,
): Array<SidebarItem> => {
  const items: Array<SidebarItem> = phases.map((phase) => ({
    key: phase.index,
    title: phase.title || `Phase ${phase.index}`,
    agents: agentsByPhaseIndex.get(phase.index) ?? [],
  }));
  const orphanAgents = agentsByPhaseIndex.get(null) ?? [];
  if (orphanAgents.length > 0) {
    items.push({ key: ORPHAN_PHASE_KEY, title: "Agents", agents: orphanAgents });
  }
  return items;
};

type AlphaWorkflowPopoverProps = {
  state?: WorkflowTaskState;
  displayName: string;
  /** The launch acknowledgement result, used as the fallback body. */
  result?: ToolResultBlock;
};

export const AlphaWorkflowPopover = ({ state, displayName, result }: AlphaWorkflowPopoverProps): ReactElement => {
  const sidebarItems = useMemo(() => {
    if (!state) return [];
    const { phases, agentsByPhaseIndex } = groupWorkflowEntriesByPhase(state);
    return buildSidebarItems(phases, agentsByPhaseIndex);
  }, [state]);

  // null = auto-follow the run: select the first phase with unfinished
  // agents (the active one), or the last phase once everything is done.
  // A click pins the selection.
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const autoKey = useMemo(() => {
    const active = sidebarItems.find((item) => item.agents.some((agent) => !isAgentDone(agent)));
    return (active ?? sidebarItems[sidebarItems.length - 1])?.key;
  }, [sidebarItems]);
  const resolvedKey = selectedKey ?? autoKey;
  const selectedItem = sidebarItems.find((item) => item.key === resolvedKey);

  if (!state) {
    // No live/replayed workflow state (e.g. the run's notification was lost).
    // Fall back to the launch acknowledgement text from the tool result.
    const launchText = result && isGenericToolContent(result.content) ? result.content.text : "";
    return (
      <div className={styles.popover} data-testid={ElementIds.ALPHA_CHAT_WORKFLOW_POPOVER}>
        <PopoverHeader title={<span className={headerStyles.titleCode}>{displayName}</span>} />
        {launchText && <div className={styles.fallbackBody}>{launchText}</div>}
      </div>
    );
  }

  const statusWord = STATUS_WORDS[state.status ?? ""] ?? state.status;
  const usage = state.usage;
  const metaParts: Array<string> = [];
  if (usage?.totalTokens !== undefined && usage?.totalTokens !== null) {
    metaParts.push(`${formatTokenCount(usage.totalTokens)} tokens`);
  }

  if (usage?.toolUses !== undefined && usage?.toolUses !== null) {
    metaParts.push(`${usage.toolUses} ${usage.toolUses === 1 ? "tool" : "tools"}`);
  }

  if (usage?.durationMs !== undefined && usage?.durationMs !== null) {
    metaParts.push(formatWorkflowDuration(usage.durationMs));
  }

  return (
    <div className={styles.popover} data-testid={ElementIds.ALPHA_CHAT_WORKFLOW_POPOVER}>
      <PopoverHeader
        title={
          <span className={styles.title}>
            <span className={headerStyles.titleCode}>{displayName}</span>
            <span className={state.status === "failed" ? styles.statusWordError : styles.statusWord}>{statusWord}</span>
          </span>
        }
        meta={metaParts.length > 0 ? metaParts.join(" · ") : undefined}
      />
      {sidebarItems.length === 0 ? (
        <div className={styles.fallbackBody}>
          {state.status === "running" ? "Starting workflow…" : "No agents ran."}
        </div>
      ) : (
        <div className={styles.body}>
          <div className={styles.sidebar}>
            <div className={styles.sidebarLabel}>Phases</div>
            {sidebarItems.map((item) => {
              const doneCount = item.agents.filter(isAgentDone).length;
              const isSelected = item.key === resolvedKey;
              return (
                <div
                  key={item.key}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  className={isSelected ? styles.phaseTabSelected : styles.phaseTab}
                  data-testid={ElementIds.ALPHA_CHAT_WORKFLOW_PHASE_TAB}
                  onClick={() => setSelectedKey(item.key)}
                  onKeyDown={activateOnEnterOrSpace(() => setSelectedKey(item.key))}
                >
                  <span className={styles.phaseStatus}>
                    <PhaseStatusIcon agents={item.agents} />
                  </span>
                  <span className={styles.phaseTitle}>{item.title}</span>
                  {/* Phases declared ahead of execution have no agents yet —
                      a "0/0" count reads like an empty phase, so hold the
                      count until agents materialize. */}
                  {item.agents.length > 0 && (
                    <span className={styles.phaseCount}>
                      {doneCount}/{item.agents.length}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <div className={styles.agentsPane}>
            {selectedItem && (
              <>
                <div className={styles.agentsPaneHeader}>
                  {selectedItem.title} · {selectedItem.agents.length}{" "}
                  {selectedItem.agents.length === 1 ? "agent" : "agents"}
                </div>
                <AgentList agents={selectedItem.agents} />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
