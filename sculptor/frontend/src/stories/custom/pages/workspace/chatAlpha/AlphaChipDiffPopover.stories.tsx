import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { ToolResultBlock } from "~/api";
import { AlphaChipDiffPopover } from "~/pages/workspace/chatAlpha/AlphaChipDiffPopover.tsx";
import { ChatAgentProvider } from "~/pages/workspace/chatAlpha/ChatAgentContext.tsx";
import type { ChipData } from "~/pages/workspace/chatAlpha/chipRow.types.ts";

const sampleDiff = `--- a/src/components/Button.tsx
+++ b/src/components/Button.tsx
@@ -10,7 +10,9 @@
 import { useState } from "react";

 export const Button = ({ label, onClick }) => {
-  const [pressed, setPressed] = useState(false);
+  const [pressed, setPressed] = useState(false);
+  const [hovered, setHovered] = useState(false);
+  const [focused, setFocused] = useState(false);

   return (
     <div onClick={onClick}>
`;

const newFileDiff = `--- /dev/null
+++ b/src/components/Modal.tsx
@@ -0,0 +1,12 @@
+import type { ReactElement } from "react";
+
+type ModalProps = {
+  isOpen: boolean;
+  onClose: () => void;
+};
+
+export const Modal = ({ isOpen, onClose }: ModalProps): ReactElement | null => {
+  if (!isOpen) return null;
+  return <div className="modal" onClick={onClose} />;
+};
`;

const makeResult = (diff: string, filePath: string): ToolResultBlock => ({
  type: "tool_result" as const,
  toolUseId: "tool-001",
  toolName: "Edit",
  invocationString: "Edit(…)",
  content: { contentType: "diff" as const, diff, filePath },
  isError: false,
});

const completedChip: ChipData = {
  id: "tool-001",
  filePath: "src/components/Button.tsx",
  displayName: "Button.tsx",
  state: "completed",
  stats: { added: 3, removed: 1 },
  isNewFile: false,
  blocks: [{ type: "tool_use", id: "tool-001", name: "Edit", input: { file_path: "src/components/Button.tsx" } }],
  results: [makeResult(sampleDiff, "src/components/Button.tsx")],
  errorDetail: null,
  errorContentType: null,
};

const completedNewFile: ChipData = {
  id: "tool-002",
  filePath: "src/components/Modal.tsx",
  displayName: "Modal.tsx",
  state: "completed",
  stats: { added: 12, removed: 0 },
  isNewFile: true,
  blocks: [{ type: "tool_use", id: "tool-002", name: "Write", input: { file_path: "src/components/Modal.tsx" } }],
  results: [makeResult(newFileDiff, "src/components/Modal.tsx")],
  errorDetail: null,
  errorContentType: null,
};

const errorChip: ChipData = {
  id: "tool-004",
  filePath: "src/lib/parser.ts",
  displayName: "parser.ts",
  state: "error",
  stats: null,
  isNewFile: false,
  blocks: [{ type: "tool_use", id: "tool-004", name: "Edit", input: { file_path: "src/lib/parser.ts" } }],
  results: [],
  errorDetail: "ENOENT: no such file or directory, open 'src/lib/parser.ts'",
  errorContentType: "text",
};

const diffErrorChip: ChipData = {
  id: "tool-007",
  filePath: "src/components/Button.tsx",
  displayName: "Button.tsx",
  state: "error",
  stats: null,
  isNewFile: false,
  blocks: [{ type: "tool_use", id: "tool-007", name: "Edit", input: { file_path: "src/components/Button.tsx" } }],
  results: [],
  errorDetail: sampleDiff,
  errorContentType: "diff",
};

const longPathChip: ChipData = {
  id: "tool-005",
  filePath: "sculptor/frontend/src/pages/workspace/chatAlpha/AlphaChipDiffPopover.tsx",
  displayName: "AlphaChipDiffPopover.tsx",
  state: "completed",
  stats: { added: 155, removed: 0 },
  isNewFile: true,
  blocks: [{ type: "tool_use", id: "tool-005", name: "Write", input: {} }],
  results: [makeResult(newFileDiff, "sculptor/frontend/src/pages/workspace/chatAlpha/AlphaChipDiffPopover.tsx")],
  errorDetail: null,
  errorContentType: null,
};

// The popover reads its workspace/agent identity from ChatAgentProvider. The
// router is still required because the popover's transitive useWorkspaceCodePath
// lookup calls useWorkspacePageParams, which throws outside a route with a
// workspaceID param.
const Wrapper = ({
  chipData,
  onClose,
  onNavigate,
}: {
  chipData: ChipData;
  onClose: () => void;
  onNavigate: (direction: "prev" | "next") => void;
}): ReactElement => (
  <MemoryRouter initialEntries={["/ws/storybook-ws/agent/storybook-agent"]}>
    <Routes>
      <Route
        path="/ws/:workspaceID/agent/:id"
        element={
          <ChatAgentProvider workspaceId="storybook-ws" agentId="storybook-agent">
            <div
              style={{ width: "520px", border: "1px solid var(--gray-a4)", borderRadius: "8px", overflow: "hidden" }}
            >
              <AlphaChipDiffPopover chipData={chipData} onClose={onClose} onNavigate={onNavigate} />
            </div>
          </ChatAgentProvider>
        }
      />
    </Routes>
  </MemoryRouter>
);

const meta = {
  title: "Chat Alpha/File Chips/AlphaChipDiffPopover",
  component: Wrapper,
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "24px" }}>
        <Story />
      </div>
    ),
  ],
  args: {
    chipData: completedChip,
    onClose: (): void => {},
    onNavigate: (): void => {},
  },
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

/** Completed edit with copy-path and open-diff icon buttons in the header. */
export const Completed: Story = {};

/** New file with "new file" badge and copy/open icon buttons. */
export const CompletedNewFile: Story = {
  args: { chipData: completedNewFile },
};

/** Error state with plain text error and a copy-error icon button. */
export const ErrorText: Story = {
  args: { chipData: errorChip },
};

/** Error state showing the attempted diff via Pierre. */
export const ErrorDiff: Story = {
  args: { chipData: diffErrorChip },
};

/** Long file path in the header to test truncation and copy behavior. */
export const LongFilePath: Story = {
  args: { chipData: longPathChip },
};
