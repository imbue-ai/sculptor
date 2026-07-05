import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import type { PillData } from "~/pages/workspace/chat/toolPill.types.ts";
import { ToolPopover } from "~/pages/workspace/chat/ToolPopover.tsx";

import {
  completedGrepOutsideWorkspacePill,
  completedGrepPill,
  completedReadOutsideWorkspacePill,
  completedReadPill,
  errorReadPill,
  executingGrepPill,
  toolResult,
  toolUse,
} from "./fixtures/tools.ts";

const WORKSPACE_CODE_PATH = "/Users/dev/work/this-project";

const multiReadPill: PillData = {
  id: "tu-100",
  label: "Read x3",
  state: "completed",
  blocks: [
    toolUse("tu-100", "Read", { file_path: "src/a.ts" }),
    toolUse("tu-101", "Read", { file_path: "src/b.ts" }),
    toolUse("tu-102", "Read", { file_path: "src/c.ts" }),
  ],
  results: [
    toolResult("tu-100", "Read", "export const a = 1;\nexport const a2 = 2;"),
    toolResult("tu-101", "Read", 'export const b = "hello";'),
    toolResult("tu-102", "Read", "export default function c() {}"),
  ],
};

const meta = {
  title: "Chat/Tools/ToolPopover",
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "24px", width: 520 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

/** Single Read tool with file content output. */
export const ReadTool: Story = {
  render: (): ReactElement => <ToolPopover pillData={completedReadPill} />,
};

/** Single Grep tool with match results. */
export const GrepTool: Story = {
  render: (): ReactElement => <ToolPopover pillData={completedGrepPill} />,
};

/** Read tool that produced an error (file not found). */
export const ErrorTool: Story = {
  render: (): ReactElement => <ToolPopover pillData={errorReadPill} />,
};

/** Executing tool (no result yet). */
export const ExecutingTool: Story = {
  render: (): ReactElement => <ToolPopover pillData={executingGrepPill} />,
};

/** Multiple entries from a grouped by-type pill. */
export const MultipleEntries: Story = {
  render: (): ReactElement => <ToolPopover pillData={multiReadPill} />,
};

/**
 * Read of a file outside the workspace. The full absolute path is shown and
 * the `folder-output` icon (with tooltip) flags it as outside.
 */
export const ReadToolOutsideWorkspace: Story = {
  render: (): ReactElement => (
    <ToolPopover pillData={completedReadOutsideWorkspacePill} workspaceCodePath={WORKSPACE_CODE_PATH} />
  ),
};

/** Grep search rooted at a directory outside the workspace. */
export const GrepToolOutsideWorkspace: Story = {
  render: (): ReactElement => (
    <ToolPopover pillData={completedGrepOutsideWorkspacePill} workspaceCodePath={WORKSPACE_CODE_PATH} />
  ),
};

/**
 * Grep with both a long pattern and a long path — exercises header wrapping
 * so the title and meta don't collide or truncate.
 */
const longGrepPill: PillData = {
  id: "tu-200",
  label: "Grep",
  state: "completed",
  blocks: [
    toolUse("tu-200", "Grep", {
      pattern: "interface DeleteConfirmationDialogProps[\\s\\S]*?\\}",
      path: "sculptor/frontend/src/components/DeleteConfirmationDialog.tsx",
    }),
  ],
  results: [toolResult("tu-200", "Grep", "")],
};

export const GrepLongPatternAndPath: Story = {
  render: (): ReactElement => <ToolPopover pillData={longGrepPill} />,
};
