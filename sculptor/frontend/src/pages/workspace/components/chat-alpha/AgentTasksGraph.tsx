import type { ReactElement } from "react";

import { AgentTaskStatus, ElementIds, type Task } from "~/api";

import styles from "./AgentTasksGraph.module.scss";
import { useTaskTiers } from "./useTaskTiers";

const COMPACT_GRAPH_THRESHOLD = 15;
const PAD = 8;
const LABEL_LINE_HEIGHT = 14;
const NODE_MIN_H = 36;
const NODE_VPAD = 8;

const nodeFill = (status: AgentTaskStatus): string => {
  if (status === AgentTaskStatus.COMPLETED) return "var(--color-success)";
  if (status === AgentTaskStatus.IN_PROGRESS) return "var(--accent-9)";
  return "transparent";
};

const nodeStroke = (status: AgentTaskStatus): string => {
  if (status === AgentTaskStatus.COMPLETED) return "var(--color-success)";
  if (status === AgentTaskStatus.IN_PROGRESS) return "var(--accent-9)";
  return "var(--accent-6)";
};

// White label on solid-filled nodes (completed green, in-progress blue);
// otherwise the default body text color over the popover background.
const nodeTextFill = (status: AgentTaskStatus): string => {
  if (status === AgentTaskStatus.COMPLETED || status === AgentTaskStatus.IN_PROGRESS) {
    return "white";
  }
  return "var(--gray-12)";
};

const truncate = (text: string, max: number): string => (text.length <= max ? text : `${text.slice(0, max - 1)}…`);

// Greedy space-aware word wrap. Each line is filled up to `charsPerLine`;
// the last line gets an ellipsis if the input couldn't fit in `maxLines`.
// A single word longer than `charsPerLine` is force-truncated on its line.
const wrapLabel = (text: string, charsPerLine: number, maxLines: number): Array<string> => {
  if (text.length <= charsPerLine) return [text];
  const words = text.split(/\s+/).filter(Boolean);
  const lines: Array<string> = [""];
  for (const word of words) {
    const i = lines.length - 1;
    const candidate = lines[i] ? `${lines[i]} ${word}` : word;
    if (candidate.length <= charsPerLine) {
      lines[i] = candidate;
    } else if (lines.length < maxLines) {
      lines.push(word.length > charsPerLine ? truncate(word, charsPerLine) : word);
    } else {
      // Out of lines — truncate the current line + remaining word so the
      // ellipsis honestly signals dropped content.
      lines[i] = truncate(candidate, charsPerLine);
      return lines;
    }
  }
  return lines.filter(Boolean);
};

export const AgentTasksGraph = ({ tasks }: { tasks: Array<Task> }): ReactElement | null => {
  const { tierById, maxTier } = useTaskTiers(tasks);

  if (tasks.length === 0) return null;

  const isCompact = tasks.length >= COMPACT_GRAPH_THRESHOLD;
  const NODE_W = isCompact ? 16 : 112;
  const COL_GAP = isCompact ? 12 : 16;
  const ROW_GAP = isCompact ? 20 : 24;
  const labelMax = isCompact ? 10 : 14;
  const maxLines = isCompact ? 1 : 2;

  // Pre-wrap every label so we can compute per-tier heights up front.
  const labelLinesById = new Map<string, Array<string>>();
  for (const task of tasks) {
    labelLinesById.set(task.id, wrapLabel(task.subject, labelMax, maxLines));
  }

  const tiers: Array<Array<Task>> = Array.from({ length: maxTier + 1 }, () => []);
  for (const task of tasks) {
    const tier = tierById.get(task.id) ?? 0;
    tiers[tier].push(task);
  }

  // Each tier sizes to the tallest label in it; tiers of short labels stay
  // compact, tiers with one long label grow only as far as that label needs.
  const tierHeights: Array<number> = tiers.map((tasksInTier) => {
    if (isCompact) return 16;
    const maxLineCount = tasksInTier.reduce((max, t) => Math.max(max, labelLinesById.get(t.id)?.length ?? 1), 1);
    return Math.max(NODE_MIN_H, maxLineCount * LABEL_LINE_HEIGHT + NODE_VPAD * 2);
  });

  const tierYOffsets: Array<number> = [];
  {
    let y = PAD;
    for (let i = 0; i < tierHeights.length; i++) {
      tierYOffsets.push(y);
      y += tierHeights[i] + ROW_GAP;
    }
  }

  const positions = new Map<string, { x: number; y: number; h: number }>();
  let maxRowWidth = 0;
  tiers.forEach((tasksInTier, tierIndex) => {
    const rowWidth = tasksInTier.length * NODE_W + Math.max(0, tasksInTier.length - 1) * COL_GAP;
    maxRowWidth = Math.max(maxRowWidth, rowWidth);
    const y = tierYOffsets[tierIndex];
    const h = tierHeights[tierIndex];
    tasksInTier.forEach((task, i) => {
      const x = PAD + i * (NODE_W + COL_GAP);
      positions.set(task.id, { x, y, h });
    });
  });

  const svgWidth = PAD * 2 + maxRowWidth;
  const lastTierBottom = tierYOffsets[tierYOffsets.length - 1] + tierHeights[tierHeights.length - 1];
  const svgHeight = lastTierBottom + PAD;

  const edges = tasks.flatMap((task) => (task.blockedBy ?? []).map((srcId) => ({ srcId, dstId: task.id })));

  return (
    <div className={styles.graphContainer}>
      <svg
        width={svgWidth}
        height={svgHeight}
        data-testid={ElementIds.AGENT_TASKS_GRAPH}
        className={styles.graphSvg}
        role="img"
        aria-label="Dependency graph for agent tasks"
      >
        {edges.map(({ srcId, dstId }, i) => {
          const src = positions.get(srcId);
          const dst = positions.get(dstId);
          if (!src || !dst) return null;
          const sx = src.x + NODE_W / 2;
          const sy = src.y + src.h;
          const dx = dst.x + NODE_W / 2;
          const dy = dst.y;
          const midY = (sy + dy) / 2;
          const d = `M ${sx} ${sy} C ${sx} ${midY}, ${dx} ${midY}, ${dx} ${dy}`;
          return <path key={`${srcId}-${dstId}-${i}`} d={d} fill="none" stroke="var(--gray-7)" strokeWidth={1} />;
        })}

        {tasks.map((task) => {
          const pos = positions.get(task.id);
          if (!pos) return null;
          const lines = labelLinesById.get(task.id) ?? [task.subject];
          const cx = pos.x + NODE_W / 2;
          const cy = pos.y + pos.h / 2;
          return (
            <g key={task.id} data-testid={ElementIds.AGENT_TASKS_GRAPH_NODE} data-task-id={task.id}>
              {isCompact ? (
                <circle
                  cx={cx}
                  cy={cy}
                  r={NODE_W / 2}
                  fill={nodeFill(task.status)}
                  stroke={nodeStroke(task.status)}
                  strokeWidth={1}
                />
              ) : (
                <rect
                  x={pos.x}
                  y={pos.y}
                  width={NODE_W}
                  height={pos.h}
                  fill={nodeFill(task.status)}
                  stroke={nodeStroke(task.status)}
                  strokeWidth={1}
                  rx={4}
                />
              )}
              {!isCompact && (
                <text textAnchor="middle" dominantBaseline="middle" fontSize={12} fill={nodeTextFill(task.status)}>
                  {lines.map((line, i) => {
                    const offset = (i - (lines.length - 1) / 2) * LABEL_LINE_HEIGHT;
                    return (
                      <tspan key={i} x={cx} y={cy + offset}>
                        {line}
                      </tspan>
                    );
                  })}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};
