import type { Meta, StoryObj } from "@storybook/react-vite";
import { Activity, CircleOff, RotateCcw } from "lucide-react";
import type { ReactElement } from "react";

import { BackgroundSystemLine } from "./BackgroundSystemLine.tsx";

const meta = {
  title: "BackgroundProcesses/BackgroundSystemLine",
  component: BackgroundSystemLine,
  globals: { theme: "dark" },
  // Constrain the width to a realistic transcript column so the right-pinned
  // time and the single-line ellipsis behavior read correctly.
  decorators: [
    (Story): ReactElement => (
      <div style={{ width: 440 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof BackgroundSystemLine>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const ProcessExit: Story = {
  args: {
    icon: CircleOff,
    name: "Background process exited",
    detail: "dev server failed (code 1)",
    time: "4m 12s",
  },
};

export const MonitorEvent: Story = {
  args: {
    icon: Activity,
    name: "Monitor event",
    detail: "CI status: still pending",
    time: "1m 02s",
  },
};

export const Restart: Story = {
  args: {
    icon: RotateCcw,
    name: "Sculptor restarted",
    detail: "2 background processes terminated  dev server · monitor: CI status",
    time: "",
  },
};
