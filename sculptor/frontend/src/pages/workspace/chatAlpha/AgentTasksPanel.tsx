import { Badge, Box, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom } from "jotai";
import { CheckSquare, Network } from "lucide-react";
import { type KeyboardEvent, type ReactElement, useCallback, useEffect, useRef, useState } from "react";

import { AgentTaskStatus, ElementIds, type Task } from "~/api";
import { mergeClasses } from "~/common/utils/classNames";
import { optional } from "~/common/utils/optional";

import { AgentTasksGraph } from "./AgentTasksGraph.tsx";
import styles from "./AgentTasksPanel.module.scss";
import { agentTasksGraphOpenAtom } from "./atoms/chatAlpha.ts";
import { useTaskTiers } from "./useTaskTiers.ts";

const MAX_INLINE_BLOCKED_BY = 2;
const FADE_DECAY_PER_TIER = 0.15;
const FADE_FLOOR = 0.4;

const computeFadeOpacity = (task: Task, liveTier: number | null, tierById: Map<string, number>): number | undefined => {
  if (task.status !== AgentTaskStatus.PENDING) return undefined;
  if (liveTier === null) return undefined;
  const distance = (tierById.get(task.id) ?? 0) - liveTier;
  if (distance <= 0) return undefined;
  return Math.max(FADE_FLOOR, 1 - FADE_DECAY_PER_TIER * (distance - 1));
};

const blockedByLabel = (ids: ReadonlyArray<string>): string => {
  if (ids.length <= MAX_INLINE_BLOCKED_BY) {
    return `Waiting on ${ids.map((id) => `#${id}`).join(", ")}`;
  }
  const head = ids.slice(0, MAX_INLINE_BLOCKED_BY);
  const remainder = ids.length - MAX_INLINE_BLOCKED_BY;
  return `Waiting on ${head.map((id) => `#${id}`).join(", ")}, +${remainder} more`;
};

const StatusIcon = ({ status }: { status: AgentTaskStatus }): ReactElement => {
  const size = 18;

  if (status === AgentTaskStatus.COMPLETED) {
    return (
      <svg width={size} height={size} viewBox="0 0 18 18" data-testid={ElementIds.ARTIFACT_PLAN_CHECKMARK}>
        <rect x="0.5" y="0.5" width="17" height="17" rx="3" fill="var(--color-success)" stroke="var(--color-success)" />
        <path
          d="M5 9l3 3 5-6"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  if (status === AgentTaskStatus.IN_PROGRESS) {
    return (
      <svg width={size} height={size} viewBox="0 0 18 18">
        <rect x="0.5" y="0.5" width="17" height="17" rx="3" fill="none" stroke="var(--accent-9)" strokeWidth="1.5" />
        <line x1="5" y1="9" x2="13" y2="9" stroke="var(--accent-9)" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // PENDING
  return (
    <svg width={size} height={size} viewBox="0 0 18 18">
      <rect x="0.5" y="0.5" width="17" height="17" rx="3" fill="none" stroke="var(--accent-6)" strokeWidth="1.5" />
    </svg>
  );
};

const WaitingBadge = ({ blockedBy }: { blockedBy: ReadonlyArray<string> }): ReactElement => (
  <Badge data-testid={ElementIds.AGENT_TASKS_WAITING_BADGE} size="1" color="gray" className={styles.waitingBadge}>
    {blockedByLabel(blockedBy)}
  </Badge>
);

const RowDetail = ({ task }: { task: Task }): ReactElement => {
  const blockedBy = task.blockedBy ?? [];
  const blocks = task.blocks ?? [];
  return (
    <div className={styles.rowDetail} data-testid={ElementIds.AGENT_TASKS_ROW_DETAIL} data-task-id={task.id}>
      {task.description && (
        <Text size="2" className={styles.detailDescription}>
          {task.description}
        </Text>
      )}
      {task.status === AgentTaskStatus.IN_PROGRESS && task.activeForm && (
        <Text size="2" color="gray" className={styles.detailActiveForm}>
          {task.activeForm}
        </Text>
      )}
      {blockedBy.length > 0 && (
        <Text size="1" color="gray">
          Waiting on:{" "}
          {blockedBy.map((id) => (
            <span key={id} className={styles.detailIdLink} onClick={(e): void => e.stopPropagation()}>
              #{id}{" "}
            </span>
          ))}
        </Text>
      )}
      {blocks.length > 0 && (
        <Text size="1" color="gray">
          Blocks:{" "}
          {blocks.map((id) => (
            <span key={id} className={styles.detailIdLink} onClick={(e): void => e.stopPropagation()}>
              #{id}{" "}
            </span>
          ))}
        </Text>
      )}
    </div>
  );
};

const TaskRow = ({
  task,
  showWaitingBadge,
  isExpanded,
  onToggle,
  fadeOpacity,
  scrollRef,
}: {
  task: Task;
  showWaitingBadge: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  fadeOpacity?: number;
  scrollRef?: (node: HTMLDivElement | null) => void;
}): ReactElement => {
  const isCompleted = task.status === AgentTaskStatus.COMPLETED;
  const isInProgress = task.status === AgentTaskStatus.IN_PROGRESS;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onToggle();
    }
  };

  return (
    <div
      ref={scrollRef}
      role="button"
      tabIndex={0}
      aria-expanded={isExpanded}
      onClick={onToggle}
      onKeyDown={handleKeyDown}
      className={styles.rowWrapper}
      style={fadeOpacity !== undefined ? { opacity: fadeOpacity } : undefined}
    >
      <Flex
        className={mergeClasses(
          styles.todoItem,
          optional(isInProgress, styles.inProgress),
          optional(isCompleted, styles.completed),
        )}
        data-testid={ElementIds.AGENT_TASKS_ROW}
      >
        <Box className={styles.iconColumn}>
          <StatusIcon status={task.status} />
        </Box>
        <Flex direction="column" gap="1" className={styles.rowBody}>
          <Text size="2" className={mergeClasses(styles.todoText, optional(isCompleted, styles.completedText))}>
            {task.subject}
          </Text>
          {showWaitingBadge && (task.blockedBy ?? []).length > 0 && <WaitingBadge blockedBy={task.blockedBy ?? []} />}
        </Flex>
      </Flex>
      {isExpanded && <RowDetail task={task} />}
    </div>
  );
};

const EmptyState = (): ReactElement => (
  <Flex
    direction="column"
    align="center"
    justify="center"
    gap="2"
    className={styles.emptyState}
    data-testid={ElementIds.AGENT_TASKS_EMPTY_STATE}
  >
    <CheckSquare size={20} color="var(--gray-7)" />
    <Text size="2" color="gray">
      No agent tasks yet
    </Text>
  </Flex>
);

const isLinearTaskList = (tasks: Array<Task>): boolean =>
  tasks.every((t) => (t.blocks ?? []).length === 0 && (t.blockedBy ?? []).length === 0);

export const AgentTasksPanel = ({ tasks }: { tasks: Array<Task> | null }): ReactElement => {
  const firstInProgressRef = useRef<HTMLDivElement | null>(null);
  const firstInProgressId = tasks?.find((t) => t.status === AgentTaskStatus.IN_PROGRESS)?.id ?? null;
  const [isGraphOpen, setIsGraphOpen] = useAtom(agentTasksGraphOpenAtom);
  const [expandedTaskIds, setExpandedTaskIds] = useState<Set<string>>(new Set());

  const { tierById, liveTier } = useTaskTiers(tasks);

  const toggleExpanded = useCallback((taskId: string) => {
    setExpandedTaskIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    firstInProgressRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [firstInProgressId]);

  if (!tasks || tasks.length === 0) {
    return <EmptyState />;
  }

  const isLinear = isLinearTaskList(tasks);
  const isToggleVisible = !isLinear && tasks.length >= 2;
  const isGraphVisible = isToggleVisible && isGraphOpen;

  const firstInProgressIndex = tasks.findIndex((t) => t.status === AgentTaskStatus.IN_PROGRESS);

  return (
    <Flex direction="column" className={styles.todoListContainer} data-graph-open={isGraphVisible ? "" : undefined}>
      {isToggleVisible && (
        <Flex align="center" justify="end" gap="2" className={styles.toggleButtonRow}>
          <Tooltip content="Toggle dependency graph">
            <IconButton
              size="1"
              variant="ghost"
              data-testid={ElementIds.AGENT_TASKS_GRAPH_TOGGLE}
              onClick={(): void => setIsGraphOpen((open) => !open)}
              aria-label="Toggle dependency graph"
              aria-pressed={isGraphOpen}
            >
              <Network size={14} />
            </IconButton>
          </Tooltip>
        </Flex>
      )}
      <Flex direction={isGraphVisible ? "row" : "column"} gap="2" className={styles.bodyColumns}>
        <div className={mergeClasses(styles.taskList, styles.listColumn)}>
          <Flex direction="column">
            {tasks.map((task, i) => {
              const ref =
                i === firstInProgressIndex
                  ? (node: HTMLDivElement | null): void => {
                      firstInProgressRef.current = node;
                    }
                  : undefined;
              return (
                <TaskRow
                  key={task.id}
                  task={task}
                  showWaitingBadge={!isLinear}
                  isExpanded={expandedTaskIds.has(task.id)}
                  onToggle={(): void => toggleExpanded(task.id)}
                  fadeOpacity={computeFadeOpacity(task, liveTier, tierById)}
                  scrollRef={ref}
                />
              );
            })}
          </Flex>
        </div>
        {isGraphVisible && (
          <div className={styles.graphColumn}>
            <AgentTasksGraph tasks={tasks} />
          </div>
        )}
      </Flex>
    </Flex>
  );
};
