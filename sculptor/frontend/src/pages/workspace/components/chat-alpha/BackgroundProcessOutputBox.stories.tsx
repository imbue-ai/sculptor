import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { action } from "storybook/actions";

import { BackgroundProcessOutputBox } from "./BackgroundProcessOutputBox.tsx";

const meta = {
  title: "BackgroundProcesses/BackgroundProcessOutputBox",
  component: BackgroundProcessOutputBox,
  globals: { theme: "dark" },
  // Constrain the width so the bounded box renders at a realistic popover size.
  decorators: [
    (Story): ReactElement => (
      <div style={{ width: 360 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof BackgroundProcessOutputBox>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

const BASH_BUILD_LINES = [
  "VITE v5.2.0  ready in 412 ms",
  "  ➜  Local:   http://localhost:5173/",
  "2:16:31 [vite] hmr update /src/.../ChatInput.tsx",
  "2:16:44 [vite] page reload src/main.tsx",
] as const;

const MONITOR_EVENT_LINES = [
  "[monitor] watching CI status for HEAD",
  "[monitor] pipeline #4821 queued",
  "[monitor] pipeline #4821 running (3 jobs)",
  "[monitor] job lint passed",
  "[monitor] job test-unit running…",
] as const;

const FAILED_RUN_LINES = [
  "$ npm run build",
  "> tsc -b && vite build",
  "src/main.tsx:14:7 - error TS2322: Type 'string' is not assignable to type 'number'.",
  "Found 1 error.",
  "exited with code 1",
] as const;

export const BashBuildLogRunning: Story = {
  args: {
    command: "npm run dev",
    lines: BASH_BUILD_LINES,
    isRunning: true,
  },
};

export const MonitorEventLog: Story = {
  args: {
    command: "monitor: CI status",
    lines: MONITOR_EVENT_LINES,
    isRunning: true,
  },
};

export const FailedRun: Story = {
  args: {
    command: "npm run build",
    lines: FAILED_RUN_LINES,
    isRunning: false,
  },
};

export const WithOpenInTerminal: Story = {
  args: {
    command: "npm run dev",
    lines: BASH_BUILD_LINES,
    isRunning: true,
    onOpenInTerminal: action("onOpenInTerminal"),
  },
};
