import type { Meta, StoryObj } from "@storybook/react-vite";
import { Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { ChatMessage } from "~/api";
import { ChatInput } from "~/pages/workspace/components/ChatInput";
import { QueuedMessageBar } from "~/pages/workspace/components/QueuedMessageBar";

// --- Sample data fixtures ---

const SHORT_MESSAGE: ChatMessage = {
  id: "msg-1",
  role: "USER",
  content: [{ type: "text", text: "Can you refactor the auth module to use JWT tokens?" }],
  approximateCreationTime: new Date().toISOString(),
};

const LONG_MESSAGE: ChatMessage = {
  id: "msg-2",
  role: "USER",
  content: [
    {
      type: "text",
      text: "Please review the entire authentication system and refactor it to use JWT tokens instead of session-based auth. Make sure to update all the middleware, add proper token rotation, handle refresh tokens, and update the tests accordingly. Also check for any security vulnerabilities in the current implementation.",
    },
  ],
  approximateCreationTime: new Date().toISOString(),
};

const MULTILINE_MESSAGE: ChatMessage = {
  id: "msg-3",
  role: "USER",
  content: [
    {
      type: "text",
      text: "Step 1: Update the database schema\nStep 2: Migrate existing data\nStep 3: Update the API endpoints\nStep 4: Fix the frontend components\nStep 5: Run the full test suite",
    },
  ],
  approximateCreationTime: new Date().toISOString(),
};

// --- Callbacks ---

const handleEditConflict = (data: {
  rawTextContent: string;
  plainTextContent: string;
  fileSources: Array<string>;
}): void => {
  console.log("Edit conflict:", data);
};

// --- Wrapper ---

const Wrapper = ({ message }: { message: ChatMessage }): ReactElement => (
  <JotaiProvider>
    <MemoryRouter initialEntries={["/ws/storybook-ws/agent/storybook-agent"]}>
      <Routes>
        <Route
          path="/ws/:workspaceID/agent/:id"
          element={
            <div style={{ width: "700px" }}>
              <QueuedMessageBar message={message} onEditConflict={handleEditConflict} />
              <ChatInput isDisabled={true} isAgentBusy={true} />
            </div>
          }
        />
      </Routes>
    </MemoryRouter>
  </JotaiProvider>
);

const meta = {
  title: "Custom/QueuedMessageBar",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    message: SHORT_MESSAGE,
  },
};

export const LongMessage: Story = {
  args: {
    message: LONG_MESSAGE,
  },
};

export const Multiline: Story = {
  args: {
    message: MULTILINE_MESSAGE,
  },
};
