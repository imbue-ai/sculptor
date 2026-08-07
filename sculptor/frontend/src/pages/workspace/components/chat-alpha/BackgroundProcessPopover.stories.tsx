import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { action } from "storybook/actions";

import type { BackgroundProcess } from "./BackgroundProcessPopover.tsx";
import { BackgroundProcessPopover } from "./BackgroundProcessPopover.tsx";

const meta = {
  title: "BackgroundProcesses/BackgroundProcessPopover",
  component: BackgroundProcessPopover,
  globals: { theme: "dark" },
  args: {
    onStopProcess: action("onStopProcess"),
  },
  // The popover is fixed-width; wrap it so it renders at its real popover size.
  decorators: [
    (Story): ReactElement => (
      <div style={{ width: 320 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof BackgroundProcessPopover>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

// Running processes derive their live elapsed from `startedAt`; anchoring it a
// fixed number of seconds before "now" keeps the stories readable without being
// perfectly frozen.
const startedSecondsAgo = (seconds: number): string => new Date(Date.now() - seconds * 1000).toISOString();

const runningProcess = (inputs: {
  taskId: string;
  kind: BackgroundProcess["kind"];
  name: string;
  startedSecondsAgo: number;
}): BackgroundProcess => ({
  taskId: inputs.taskId,
  toolUseId: `tool-${inputs.taskId}`,
  kind: inputs.kind,
  name: inputs.name,
  status: "running",
  startedAt: startedSecondsAgo(inputs.startedSecondsAgo),
  endedAt: null,
  summary: "",
  durationSeconds: null,
});

const endedProcess = (inputs: {
  taskId: string;
  kind: BackgroundProcess["kind"];
  name: string;
  status: "completed" | "failed" | "stopped";
  durationSeconds: number;
}): BackgroundProcess => ({
  taskId: inputs.taskId,
  toolUseId: `tool-${inputs.taskId}`,
  kind: inputs.kind,
  name: inputs.name,
  status: inputs.status,
  startedAt: startedSecondsAgo(inputs.durationSeconds + 30),
  endedAt: startedSecondsAgo(30),
  summary: "",
  durationSeconds: inputs.durationSeconds,
});

const DEV_SERVER_OUTPUT = {
  command: "npm run dev",
  lines: [
    "VITE v5.2.0  ready in 412 ms",
    "  ➜  Local:   http://localhost:5173/",
    "2:16:31 [vite] hmr update /src/.../ChatInput.tsx",
    "2:16:44 [vite] page reload src/main.tsx",
  ],
} as const;

const MONITOR_OUTPUT = {
  command: "monitor: CI status",
  lines: [
    "[monitor] watching CI status for HEAD",
    "[monitor] pipeline #4821 running (3 jobs)",
    "[monitor] job lint passed",
    "[monitor] job test-unit running…",
  ],
} as const;

// In the product every background process has a tailed output file, so every
// row is expandable and shows the caret. Build a matching output map for a set
// of processes. The collapsed stories don't render the body (only the caret),
// so a light per-row entry suffices; RowExpandedWithOutput supplies richer
// output for the row it opens.
const outputsFor = (
  processes: ReadonlyArray<BackgroundProcess>,
): Record<string, { command: string; lines: ReadonlyArray<string> }> =>
  Object.fromEntries(processes.map((process) => [process.taskId, { command: process.name, lines: ["…"] }]));

const SINGLE_PROCESSES: ReadonlyArray<BackgroundProcess> = [
  runningProcess({ taskId: "p1", kind: "bash", name: "dev server", startedSecondsAgo: 134 }),
];

export const SingleRunningBash: Story = {
  args: { processes: SINGLE_PROCESSES, outputByTaskId: outputsFor(SINGLE_PROCESSES) },
};

const BASH_MONITOR_AGENT_PROCESSES: ReadonlyArray<BackgroundProcess> = [
  runningProcess({ taskId: "p1", kind: "bash", name: "dev server", startedSecondsAgo: 134 }),
  runningProcess({ taskId: "p2", kind: "monitor", name: "monitor · CI status", startedSecondsAgo: 62 }),
  runningProcess({ taskId: "p3", kind: "agent", name: "refactor file picker", startedSecondsAgo: 198 }),
];

export const RunningBashMonitorAgent: Story = {
  args: { processes: BASH_MONITOR_AGENT_PROCESSES, outputByTaskId: outputsFor(BASH_MONITOR_AGENT_PROCESSES) },
};

const MIXED_PROCESSES: ReadonlyArray<BackgroundProcess> = [
  runningProcess({ taskId: "p1", kind: "bash", name: "dev server", startedSecondsAgo: 134 }),
  runningProcess({ taskId: "p2", kind: "monitor", name: "monitor · CI status", startedSecondsAgo: 62 }),
  endedProcess({ taskId: "p3", kind: "agent", name: "summarize changelog", status: "completed", durationSeconds: 362 }),
  endedProcess({ taskId: "p4", kind: "bash", name: "build", status: "failed", durationSeconds: 252 }),
  endedProcess({ taskId: "p5", kind: "monitor", name: "monitor · deploy", status: "stopped", durationSeconds: 88 }),
];

export const MixedRunningAndEnded: Story = {
  args: { processes: MIXED_PROCESSES, outputByTaskId: outputsFor(MIXED_PROCESSES) },
};

const SCALED_PROCESSES: ReadonlyArray<BackgroundProcess> = [
  runningProcess({ taskId: "p1", kind: "bash", name: "dev server", startedSecondsAgo: 312 }),
  runningProcess({ taskId: "p2", kind: "monitor", name: "monitor · CI status", startedSecondsAgo: 281 }),
  runningProcess({ taskId: "p3", kind: "agent", name: "refactor file picker", startedSecondsAgo: 240 }),
  runningProcess({ taskId: "p4", kind: "bash", name: "tail server logs", startedSecondsAgo: 190 }),
  runningProcess({ taskId: "p5", kind: "monitor", name: "monitor · deploy", startedSecondsAgo: 121 }),
  runningProcess({ taskId: "p6", kind: "agent", name: "write release notes", startedSecondsAgo: 64 }),
  endedProcess({ taskId: "p7", kind: "bash", name: "npm install", status: "completed", durationSeconds: 73 }),
  endedProcess({ taskId: "p8", kind: "bash", name: "build", status: "failed", durationSeconds: 252 }),
  endedProcess({ taskId: "p9", kind: "agent", name: "summarize PR", status: "completed", durationSeconds: 142 }),
  endedProcess({
    taskId: "p10",
    kind: "monitor",
    name: "monitor · queue depth",
    status: "stopped",
    durationSeconds: 410,
  }),
];

export const ScaledList: Story = {
  args: { processes: SCALED_PROCESSES, outputByTaskId: outputsFor(SCALED_PROCESSES) },
};

const EXPANDED_PROCESSES: ReadonlyArray<BackgroundProcess> = [
  runningProcess({ taskId: "p1", kind: "bash", name: "dev server", startedSecondsAgo: 134 }),
  runningProcess({ taskId: "p2", kind: "monitor", name: "monitor · CI status", startedSecondsAgo: 62 }),
];

export const RowExpandedWithOutput: Story = {
  args: {
    processes: EXPANDED_PROCESSES,
    outputByTaskId: { p1: DEV_SERVER_OUTPUT, p2: MONITOR_OUTPUT },
    initialExpandedTaskId: "p1",
  },
};

export const RunningRowWithStop: Story = {
  args: { processes: SINGLE_PROCESSES, outputByTaskId: outputsFor(SINGLE_PROCESSES) },
};
