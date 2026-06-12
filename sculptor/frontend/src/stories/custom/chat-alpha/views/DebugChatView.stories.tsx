import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { DebugChatView } from "~/pages/workspace/components/chat-alpha/DebugChatView.tsx";

import {
  basicConversation,
  contextManagement,
  errorsAndWarnings,
  kitchenSink,
  subagentNesting,
  toolExecution,
} from "../fixtures/scenarios.ts";

const meta = {
  title: "Chat Alpha/Views/DebugChatView",
  component: DebugChatView,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    messages: basicConversation(),
  },
  decorators: [
    (Story): ReactElement => (
      <div style={{ height: "500px", display: "flex" }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof DebugChatView>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const WithMessages: Story = {};

export const Empty: Story = {
  args: { messages: [] },
};

export const Tools: Story = {
  args: { messages: toolExecution() },
};

export const ErrorsAndWarnings: Story = {
  args: { messages: errorsAndWarnings() },
};

export const ContextManagement: Story = {
  args: { messages: contextManagement() },
};

export const Subagents: Story = {
  args: { messages: subagentNesting() },
};

export const KitchenSink: Story = {
  args: { messages: kitchenSink() },
};
