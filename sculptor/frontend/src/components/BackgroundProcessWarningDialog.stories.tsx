import type { Meta, StoryObj } from "@storybook/react-vite";
import { action } from "storybook/actions";

import { BackgroundProcessWarningDialog } from "./BackgroundProcessWarningDialog.tsx";

const meta = {
  title: "BackgroundProcesses/BackgroundProcessWarningDialog",
  component: BackgroundProcessWarningDialog,
  globals: { theme: "dark" },
  args: {
    isOpen: true,
    onOpenChange: action("onOpenChange"),
    onConfirm: action("onConfirm"),
  },
} satisfies Meta<typeof BackgroundProcessWarningDialog>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const QuitWithRunning: Story = {
  args: {
    action: "quit",
    runningCount: 3,
  },
};

export const DeleteAgentWithRunning: Story = {
  args: {
    action: "delete-agent",
    runningCount: 1,
    entityName: "fix-auth-bug",
  },
};

export const DeleteWorkspaceNoneRunning: Story = {
  args: {
    action: "delete-workspace",
    runningCount: 0,
  },
};

export const DeleteWorkspaceWithRunning: Story = {
  args: {
    action: "delete-workspace",
    runningCount: 2,
  },
};
