import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { BackgroundToolBlock } from "./BackgroundToolBlock.tsx";

const meta = {
  title: "BackgroundProcesses/BackgroundToolBlock",
  component: BackgroundToolBlock,
  globals: { theme: "dark" },
  // Constrain the width to a realistic transcript column, and add left padding
  // so the negatively-positioned gutter icon (spinner / corner-return) is
  // visible — it sits in the chat's left gutter, outside the pill.
  decorators: [
    (Story): ReactElement => (
      <div style={{ width: 440, paddingLeft: 28 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof BackgroundToolBlock>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

const BASH_BUILD_LINES = [
  "$ npm run build",
  "> tsc -b && vite build",
  "src/main.tsx:14:7 - error TS2322: Type 'string' is not assignable to type 'number'.",
  "Found 1 error.",
  "exited with code 1",
] as const;

const MONITOR_EVENT_LINES = [
  "[monitor] watching CI status for HEAD",
  "[monitor] pipeline #4821 queued",
  "[monitor] pipeline #4821 running (3 jobs)",
  "[monitor] job lint passed",
  "[monitor] job test-unit running…",
] as const;

export const BashRunning: Story = {
  args: {
    kind: "bash",
    name: "dev server",
    command: "npm run dev",
    status: "running",
    trailingText: "background · 2m 14s",
  },
};

export const BashExitedExpanded: Story = {
  args: {
    kind: "bash",
    name: "build",
    command: "npm run build",
    status: "exited",
    trailingText: "exited · code 1 · 4m 12s",
    exitCode: 1,
    isExpanded: true,
    output: {
      command: "npm run build",
      lines: BASH_BUILD_LINES,
    },
  },
};

export const MonitorRunningExpanded: Story = {
  args: {
    kind: "monitor",
    name: "CI status",
    command: "monitor: CI status",
    status: "running",
    trailingText: "background · 1m 02s",
    isExpanded: true,
    output: {
      command: "monitor: CI status",
      lines: MONITOR_EVENT_LINES,
    },
  },
};

export const AgentRunning: Story = {
  args: {
    kind: "agent",
    name: "Refactor the auth module and add tests",
    command: "Refactor the auth module and add tests",
    status: "running",
    trailingText: "background · 3m 18s",
  },
};

export const AgentDone: Story = {
  args: {
    kind: "agent",
    name: "Refactor the auth module and add tests",
    command: "Refactor the auth module and add tests",
    status: "done",
    trailingText: "done · 6m 02s",
  },
};
