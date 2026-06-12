import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AlphaSubagentPopover } from "~/pages/workspace/components/chat-alpha/AlphaSubagentPopover.tsx";

import { completedSubagent, noToolsSubagent, thinkingSubagent } from "../tools/fixtures.ts";

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Chat Alpha/Subagents/AlphaSubagentPopover",
  decorators: [
    (Story): ReactElement => (
      <MemoryRouter initialEntries={["/ws/storybook-ws/agent/storybook-agent"]}>
        <Routes>
          <Route
            path="/ws/:workspaceID/agent/:id"
            element={
              <div style={{ padding: "24px", width: 560 }}>
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

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** Completed subagent with prompt, tools, and response sections. */
export const Completed: Story = {
  render: (): ReactElement => (
    <AlphaSubagentPopover
      parentBlock={completedSubagent.parentBlock}
      childNodes={completedSubagent.childNodes}
      toolResultMap={completedSubagent.toolResultMap}
      metadata={completedSubagent.metadata.get(completedSubagent.parentBlock.id)}
      isThinking={false}
    />
  ),
};

/** Subagent still thinking, showing animation and "Thinking..." label. */
export const Thinking: Story = {
  render: (): ReactElement => (
    <AlphaSubagentPopover
      parentBlock={thinkingSubagent.parentBlock}
      childNodes={thinkingSubagent.childNodes}
      toolResultMap={thinkingSubagent.toolResultMap}
      metadata={thinkingSubagent.metadata.get(thinkingSubagent.parentBlock.id)}
      isThinking={true}
    />
  ),
};

/** Completed subagent with no tools — just prompt and response. */
export const NoTools: Story = {
  render: (): ReactElement => (
    <AlphaSubagentPopover
      parentBlock={noToolsSubagent.parentBlock}
      childNodes={noToolsSubagent.childNodes}
      toolResultMap={noToolsSubagent.toolResultMap}
      metadata={noToolsSubagent.metadata.get(noToolsSubagent.parentBlock.id)}
      isThinking={false}
    />
  ),
};
