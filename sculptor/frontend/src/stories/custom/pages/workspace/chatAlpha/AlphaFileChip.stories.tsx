import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { useState } from "react";

import { AlphaFileChip } from "~/pages/workspace/chatAlpha/AlphaFileChip.tsx";
import type { ChipData } from "~/pages/workspace/chatAlpha/chipRow.types.ts";

const completedChip: ChipData = {
  id: "tool-001",
  filePath: "src/components/Button.tsx",
  displayName: "Button.tsx",
  state: "completed",
  stats: { added: 12, removed: 3 },
  isNewFile: false,
  blocks: [{ type: "tool_use", id: "tool-001", name: "Edit", input: { file_path: "src/components/Button.tsx" } }],
  results: [],
  errorDetail: null,
  errorContentType: null,
};

const executingChip: ChipData = {
  id: "tool-002",
  filePath: "src/utils/format.ts",
  displayName: "format.ts",
  state: "executing",
  stats: null,
  isNewFile: false,
  blocks: [{ type: "tool_use", id: "tool-002", name: "Edit", input: { file_path: "src/utils/format.ts" } }],
  results: [],
  errorDetail: null,
  errorContentType: null,
};

const errorChip: ChipData = {
  id: "tool-003",
  filePath: "src/lib/parser.ts",
  displayName: "parser.ts",
  state: "error",
  stats: null,
  isNewFile: false,
  blocks: [{ type: "tool_use", id: "tool-003", name: "Edit", input: { file_path: "src/lib/parser.ts" } }],
  results: [],
  errorDetail: "File not found: src/lib/parser.ts",
  errorContentType: "text",
};

const newFileChip: ChipData = {
  id: "tool-004",
  filePath: "src/components/Modal.tsx",
  displayName: "Modal.tsx",
  state: "completed",
  stats: { added: 45, removed: 0 },
  isNewFile: true,
  blocks: [{ type: "tool_use", id: "tool-004", name: "Write", input: { file_path: "src/components/Modal.tsx" } }],
  results: [],
  errorDetail: null,
  errorContentType: null,
};

const largeStatsChip: ChipData = {
  id: "tool-005",
  filePath: "src/pages/workspace/chatAlpha/AlphaChatView.tsx",
  displayName: "chatAlpha/AlphaChatView.tsx",
  state: "completed",
  stats: { added: 247, removed: 89 },
  isNewFile: false,
  blocks: [{ type: "tool_use", id: "tool-005", name: "Edit", input: {} }],
  results: [],
  errorDetail: null,
  errorContentType: null,
};

// Manages open/toggle state for Storybook.
const InteractiveChip = ({ chipData }: { chipData: ChipData }): ReactElement => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <AlphaFileChip
      chipData={chipData}
      isOpen={isOpen}
      onToggle={() => setIsOpen((o) => !o)}
      onFocus={() => {}}
      tabIndex={0}
    />
  );
};

const meta = {
  title: "Chat Alpha/File Chips/AlphaFileChip",
  component: AlphaFileChip,
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "24px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
        <Story />
      </div>
    ),
  ],
  args: {
    chipData: completedChip,
    isOpen: false,
    onToggle: (): void => {},
    onFocus: (): void => {},
    tabIndex: 0 as const,
  },
} satisfies Meta<typeof AlphaFileChip>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Completed: Story = {};

export const Executing: Story = {
  args: { chipData: executingChip },
};

export const Error: Story = {
  args: { chipData: errorChip },
};

export const NewFile: Story = {
  args: { chipData: newFileChip },
};

export const Open: Story = {
  args: { chipData: completedChip, isOpen: true },
};

export const LargeStats: Story = {
  args: { chipData: largeStatsChip },
};

/** All states side by side for visual comparison. */
export const AllStates: Story = {
  render: (): ReactElement => (
    <>
      <InteractiveChip chipData={completedChip} />
      <InteractiveChip chipData={executingChip} />
      <InteractiveChip chipData={errorChip} />
      <InteractiveChip chipData={newFileChip} />
      <InteractiveChip chipData={largeStatsChip} />
    </>
  ),
};
