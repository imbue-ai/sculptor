import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { useState } from "react";

import { AlphaToolPill } from "~/pages/workspace/components/chat-alpha/AlphaToolPill.tsx";
import type { PillData } from "~/pages/workspace/components/chat-alpha/toolPill.types.ts";

import {
  completedGlobPill,
  completedGrepOutsideWorkspacePill,
  completedGrepPill,
  completedLsPill,
  completedNotebookReadPill,
  completedReadOutsideWorkspacePill,
  completedReadPill,
  completedSkillPill,
  completedWebFetchPill,
  completedWebSearchPill,
  errorReadPill,
  executingGrepPill,
} from "./fixtures.ts";

// ---------------------------------------------------------------------------
// Interactive wrapper
// ---------------------------------------------------------------------------

const InteractivePill = ({ pillData }: { pillData: PillData }): ReactElement => {
  const [isOpen, setIsOpen] = useState(false);
  return <AlphaToolPill pillData={pillData} isOpen={isOpen} onToggle={() => setIsOpen((o) => !o)} />;
};

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Chat Alpha/Tools/AlphaToolPill",
  component: AlphaToolPill,
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "24px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
        <Story />
      </div>
    ),
  ],
  args: {
    pillData: completedReadPill,
    isOpen: false,
    onToggle: (): void => {},
  },
} satisfies Meta<typeof AlphaToolPill>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories — one per tool type that renders as a pill
// ---------------------------------------------------------------------------

export const CompletedRead: Story = {};

export const CompletedGrep: Story = {
  args: { pillData: completedGrepPill },
};

export const CompletedGlob: Story = {
  args: { pillData: completedGlobPill },
};

export const CompletedLS: Story = {
  args: { pillData: completedLsPill },
};

export const CompletedWebFetch: Story = {
  args: { pillData: completedWebFetchPill },
};

export const CompletedWebSearch: Story = {
  args: { pillData: completedWebSearchPill },
};

export const CompletedSkill: Story = {
  args: { pillData: completedSkillPill },
};

export const CompletedNotebookRead: Story = {
  args: { pillData: completedNotebookReadPill },
};

/**
 * Read of a file living outside the workspace code path: the full absolute
 * path is shown and the `folder-output` icon (with tooltip) flags it.
 */
export const CompletedReadOutsideWorkspace: Story = {
  args: { pillData: completedReadOutsideWorkspacePill },
};

/** Same indicator on a Grep pill where the search path is outside the workspace. */
export const CompletedGrepOutsideWorkspace: Story = {
  args: { pillData: completedGrepOutsideWorkspacePill },
};

// ---------------------------------------------------------------------------
// State variants
// ---------------------------------------------------------------------------

export const Executing: Story = {
  args: { pillData: executingGrepPill },
};

export const Error: Story = {
  args: { pillData: errorReadPill },
};

export const Open: Story = {
  args: { pillData: completedReadPill, isOpen: true },
};

/** All tool types and states side by side for visual comparison. */
export const AllStates: Story = {
  render: (): ReactElement => (
    <>
      <InteractivePill pillData={completedReadPill} />
      <InteractivePill pillData={completedGrepPill} />
      <InteractivePill pillData={completedGlobPill} />
      <InteractivePill pillData={completedLsPill} />
      <InteractivePill pillData={completedWebFetchPill} />
      <InteractivePill pillData={completedWebSearchPill} />
      <InteractivePill pillData={completedSkillPill} />
      <InteractivePill pillData={completedNotebookReadPill} />
      <InteractivePill pillData={completedReadOutsideWorkspacePill} />
      <InteractivePill pillData={completedGrepOutsideWorkspacePill} />
      <InteractivePill pillData={executingGrepPill} />
      <InteractivePill pillData={errorReadPill} />
    </>
  ),
};
