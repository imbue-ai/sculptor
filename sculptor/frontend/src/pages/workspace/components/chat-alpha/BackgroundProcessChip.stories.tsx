import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { BackgroundProcessChipButton } from "./BackgroundProcessChip.tsx";

const meta = {
  title: "BackgroundProcesses/BackgroundProcessChip",
  component: BackgroundProcessChipButton,
  globals: { theme: "dark" },
} satisfies Meta<typeof BackgroundProcessChipButton>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const OneProcessClosed: Story = {
  args: { runningCount: 1, isOpen: false },
};

export const OneProcessOpen: Story = {
  args: { runningCount: 1, isOpen: true },
};

export const TwoProcessesClosed: Story = {
  args: { runningCount: 2, isOpen: false },
};

export const TwoProcessesOpen: Story = {
  args: { runningCount: 2, isOpen: true },
};

export const AllVariants: Story = {
  args: { runningCount: 1, isOpen: false },
  render: (): ReactElement => (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", alignItems: "flex-start" }}>
      <BackgroundProcessChipButton runningCount={1} isOpen={false} />
      <BackgroundProcessChipButton runningCount={1} isOpen={true} />
      <BackgroundProcessChipButton runningCount={2} isOpen={false} />
      <BackgroundProcessChipButton runningCount={2} isOpen={true} />
    </div>
  ),
};
