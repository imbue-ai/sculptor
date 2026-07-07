import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { AlphaToolPopover } from "~/pages/workspace/components/chat-alpha/AlphaToolPopover.tsx";
import type { PillData } from "~/pages/workspace/components/chat-alpha/toolPill.types.ts";

import {
  completedGrepOutsideWorkspacePill,
  completedGrepPill,
  completedReadOutsideWorkspacePill,
  completedReadPill,
  errorReadPill,
  executingGrepPill,
  toolResult,
  toolUse,
} from "./fixtures.ts";

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
  title: "Chat Alpha/Tools/AlphaToolPopover",
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
  render: (): ReactElement => <AlphaToolPopover pillData={completedReadPill} />,
};

/** Single Grep tool with match results. */
export const GrepTool: Story = {
  render: (): ReactElement => <AlphaToolPopover pillData={completedGrepPill} />,
};

/** Read tool that produced an error (file not found). */
export const ErrorTool: Story = {
  render: (): ReactElement => <AlphaToolPopover pillData={errorReadPill} />,
};

/** Executing tool (no result yet). */
export const ExecutingTool: Story = {
  render: (): ReactElement => <AlphaToolPopover pillData={executingGrepPill} />,
};

/** Multiple entries from a grouped by-type pill. */
export const MultipleEntries: Story = {
  render: (): ReactElement => <AlphaToolPopover pillData={multiReadPill} />,
};

/**
 * Read of a file outside the workspace. The full absolute path is shown and
 * the `folder-output` icon (with tooltip) flags it as outside.
 */
export const ReadToolOutsideWorkspace: Story = {
  render: (): ReactElement => (
    <AlphaToolPopover pillData={completedReadOutsideWorkspacePill} workspaceCodePath={WORKSPACE_CODE_PATH} />
  ),
};

/** Grep search rooted at a directory outside the workspace. */
export const GrepToolOutsideWorkspace: Story = {
  render: (): ReactElement => (
    <AlphaToolPopover pillData={completedGrepOutsideWorkspacePill} workspaceCodePath={WORKSPACE_CODE_PATH} />
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
      pattern: "type ConfirmationDialogProps[\\s\\S]*?\\}",
      path: "sculptor/frontend/src/components/ConfirmationDialog.tsx",
    }),
  ],
  results: [toolResult("tu-200", "Grep", "")],
};

export const GrepLongPatternAndPath: Story = {
  render: (): ReactElement => <AlphaToolPopover pillData={longGrepPill} />,
};
