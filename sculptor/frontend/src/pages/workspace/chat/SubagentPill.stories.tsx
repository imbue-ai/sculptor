import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import {
  backgroundCompletedSubagent,
  backgroundThinkingSubagent,
  completedSubagent,
  noToolsSubagent,
  thinkingSubagent,
} from "./fixtures/tools.ts";
import { SubagentPill } from "./SubagentPill.tsx";

const meta = {
  title: "Chat/Subagents/SubagentPill",
  decorators: [
    (Story): ReactElement => (
      <MemoryRouter initialEntries={["/ws/storybook-ws/agent/storybook-agent"]}>
        <Routes>
          <Route
            path="/ws/:workspaceID/agent/:id"
            element={
              <div style={{ padding: "24px", maxWidth: 600 }}>
                <Story />
              </div>
            }
          />
        </Routes>
      </MemoryRouter>
    ),
  ],
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

/** Completed Explore subagent with tools and a response. */
export const Completed: Story = {
  render: (): ReactElement => (
    <SubagentPill
      parentBlock={completedSubagent.parentBlock}
      childNodes={completedSubagent.childNodes}
      toolResultMap={completedSubagent.toolResultMap}
      subagentMetadataMap={completedSubagent.metadata}
    />
  ),
};

/** Subagent that is still thinking (no response text yet). */
export const Thinking: Story = {
  render: (): ReactElement => (
    <SubagentPill
      parentBlock={thinkingSubagent.parentBlock}
      childNodes={thinkingSubagent.childNodes}
      toolResultMap={thinkingSubagent.toolResultMap}
      subagentMetadataMap={thinkingSubagent.metadata}
    />
  ),
};

/** Completed subagent with no tools (text-only response). */
export const NoTools: Story = {
  render: (): ReactElement => (
    <SubagentPill
      parentBlock={noToolsSubagent.parentBlock}
      childNodes={noToolsSubagent.childNodes}
      toolResultMap={noToolsSubagent.toolResultMap}
      subagentMetadataMap={noToolsSubagent.metadata}
    />
  ),
};

/** Completed subagent launched in the background. */
export const BackgroundCompleted: Story = {
  render: (): ReactElement => (
    <SubagentPill
      parentBlock={backgroundCompletedSubagent.parentBlock}
      childNodes={backgroundCompletedSubagent.childNodes}
      toolResultMap={backgroundCompletedSubagent.toolResultMap}
      subagentMetadataMap={backgroundCompletedSubagent.metadata}
    />
  ),
};

/** Background subagent still thinking. */
export const BackgroundThinking: Story = {
  render: (): ReactElement => (
    <SubagentPill
      parentBlock={backgroundThinkingSubagent.parentBlock}
      childNodes={backgroundThinkingSubagent.childNodes}
      toolResultMap={backgroundThinkingSubagent.toolResultMap}
      subagentMetadataMap={backgroundThinkingSubagent.metadata}
    />
  ),
};

/** All variants stacked for comparison. */
export const AllStates: Story = {
  render: (): ReactElement => (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <SubagentPill
        parentBlock={completedSubagent.parentBlock}
        childNodes={completedSubagent.childNodes}
        toolResultMap={completedSubagent.toolResultMap}
        subagentMetadataMap={completedSubagent.metadata}
      />
      <SubagentPill
        parentBlock={thinkingSubagent.parentBlock}
        childNodes={thinkingSubagent.childNodes}
        toolResultMap={thinkingSubagent.toolResultMap}
        subagentMetadataMap={thinkingSubagent.metadata}
      />
      <SubagentPill
        parentBlock={noToolsSubagent.parentBlock}
        childNodes={noToolsSubagent.childNodes}
        toolResultMap={noToolsSubagent.toolResultMap}
        subagentMetadataMap={noToolsSubagent.metadata}
      />
    </div>
  ),
};
