import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { AlphaChipRow } from "~/pages/workspace/components/chat-alpha/AlphaChipRow.tsx";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const toolUse = (id: string, name: string, filePath: string): ToolUseBlock =>
  ({ type: "tool_use", id, name, input: { file_path: filePath } }) as unknown as ToolUseBlock;

const toolResult = (
  toolUseId: string,
  toolName: string,
  diff: string,
  filePath: string,
  isError = false,
): ToolResultBlock =>
  ({
    type: "tool_result",
    toolUseId,
    toolName,
    invocationString: `${toolName}(…)`,
    content: isError
      ? { contentType: "generic", text: "Error: file not found" }
      : { contentType: "diff", diff, filePath },
    isError,
  }) as unknown as ToolResultBlock;

const sampleDiff = `--- a/src/components/Button.tsx
+++ b/src/components/Button.tsx
@@ -10,7 +10,9 @@
 import { useState } from "react";

 export const Button = ({ label }) => {
-  const [pressed, setPressed] = useState(false);
+  const [pressed, setPressed] = useState(false);
+  const [hovered, setHovered] = useState(false);
+  const [focused, setFocused] = useState(false);

   return <span>{label}</span>;
 };
`;

const newFileDiff = `--- /dev/null
+++ b/src/components/Modal.tsx
@@ -0,0 +1,8 @@
+import type { ReactElement } from "react";
+
+export const Modal = (): ReactElement => (
+  <div className="modal">
+    <h2>Title</h2>
+    <p>Body</p>
+  </div>
+);
`;

// ---------------------------------------------------------------------------
// Fixtures: block arrays + result maps
// ---------------------------------------------------------------------------

// Single completed edit
const singleBlocks: Array<ToolUseBlock> = [toolUse("t-001", "Edit", "src/components/Button.tsx")];
const singleResults = new Map<string, ToolResultBlock>([
  ["t-001", toolResult("t-001", "Edit", sampleDiff, "src/components/Button.tsx")],
]);

// Multiple completed edits to different files
const multiBlocks: Array<ToolUseBlock> = [
  toolUse("t-010", "Edit", "src/components/Button.tsx"),
  toolUse("t-011", "Write", "src/components/Modal.tsx"),
  toolUse("t-012", "Edit", "src/utils/helpers.ts"),
];
const multiResults = new Map<string, ToolResultBlock>([
  ["t-010", toolResult("t-010", "Edit", sampleDiff, "src/components/Button.tsx")],
  ["t-011", toolResult("t-011", "Write", newFileDiff, "src/components/Modal.tsx")],
  ["t-012", toolResult("t-012", "Edit", sampleDiff, "src/utils/helpers.ts")],
]);

// Mix of completed and executing
const mixedBlocks: Array<ToolUseBlock> = [
  toolUse("t-020", "Edit", "src/components/Button.tsx"),
  toolUse("t-021", "Edit", "src/utils/format.ts"),
  toolUse("t-022", "Write", "src/components/NewWidget.tsx"),
];
const mixedResults = new Map<string, ToolResultBlock>([
  ["t-020", toolResult("t-020", "Edit", sampleDiff, "src/components/Button.tsx")],
]);

// Error state
const errorBlocks: Array<ToolUseBlock> = [
  toolUse("t-030", "Edit", "src/components/Button.tsx"),
  toolUse("t-031", "Edit", "src/lib/missing.ts"),
];
const errorResults = new Map<string, ToolResultBlock>([
  ["t-030", toolResult("t-030", "Edit", sampleDiff, "src/components/Button.tsx")],
  ["t-031", toolResult("t-031", "Edit", "", "src/lib/missing.ts", true)],
]);

// Same file edited multiple times (should merge into one chip)
const mergedBlocks: Array<ToolUseBlock> = [
  toolUse("t-040", "Edit", "src/components/Button.tsx"),
  toolUse("t-041", "Edit", "src/components/Button.tsx"),
];
const mergedResults = new Map<string, ToolResultBlock>([
  ["t-040", toolResult("t-040", "Edit", sampleDiff, "src/components/Button.tsx")],
  ["t-041", toolResult("t-041", "Edit", sampleDiff, "src/components/Button.tsx")],
]);

// Duplicate basenames — should disambiguate display names
const disambiguatedBlocks: Array<ToolUseBlock> = [
  toolUse("t-050", "Edit", "src/components/Button.tsx"),
  toolUse("t-051", "Edit", "src/legacy/Button.tsx"),
  toolUse("t-052", "Edit", "src/utils/helpers.ts"),
];
const disambiguatedResults = new Map<string, ToolResultBlock>([
  ["t-050", toolResult("t-050", "Edit", sampleDiff, "src/components/Button.tsx")],
  ["t-051", toolResult("t-051", "Edit", sampleDiff, "src/legacy/Button.tsx")],
  ["t-052", toolResult("t-052", "Edit", sampleDiff, "src/utils/helpers.ts")],
]);

// Many files for wrapping
const manyBlocks: Array<ToolUseBlock> = Array.from({ length: 8 }, (_, i) =>
  toolUse(`t-06${i}`, "Edit", `src/files/file${i + 1}.ts`),
);
const manyResults = new Map<string, ToolResultBlock>(
  manyBlocks.map((b) => [b.id, toolResult(b.id, "Edit", sampleDiff, (b.input as { file_path: string }).file_path)]),
);

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

type WrapperProps = {
  blocks: ReadonlyArray<ToolUseBlock>;
  toolResultMap: Map<string, ToolResultBlock>;
  inProgressMessageId: string | null;
};

const Wrapper = ({ blocks, toolResultMap, inProgressMessageId }: WrapperProps): ReactElement => (
  <MemoryRouter initialEntries={["/ws/storybook-ws/agent/storybook-agent"]}>
    <Routes>
      <Route
        path="/ws/:workspaceID/agent/:id"
        element={
          <div style={{ maxWidth: "600px" }}>
            <AlphaChipRow blocks={blocks} toolResultMap={toolResultMap} inProgressMessageId={inProgressMessageId} />
          </div>
        }
      />
    </Routes>
  </MemoryRouter>
);

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Chat Alpha/File Chips/AlphaChipRow",
  component: Wrapper,
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "24px" }}>
        <Story />
      </div>
    ),
  ],
  args: {
    blocks: singleBlocks,
    toolResultMap: singleResults,
    inProgressMessageId: null,
  },
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** Single completed chip. Click to open popover. */
export const SingleChip: Story = {};

/** Multiple completed chips for different files. */
export const MultipleChips: Story = {
  args: { blocks: multiBlocks, toolResultMap: multiResults },
};

/** Mix of completed and executing chips (in-progress message). */
export const MixedStates: Story = {
  args: {
    blocks: mixedBlocks,
    toolResultMap: mixedResults,
    inProgressMessageId: "msg-active",
  },
};

/** One completed chip and one error chip. */
export const WithError: Story = {
  args: { blocks: errorBlocks, toolResultMap: errorResults },
};

/** Two edits to the same file merged into one chip. */
export const MergedSameFile: Story = {
  args: { blocks: mergedBlocks, toolResultMap: mergedResults },
};

/** Duplicate basenames get parent-directory prefix in display name. */
export const DisambiguatedNames: Story = {
  args: { blocks: disambiguatedBlocks, toolResultMap: disambiguatedResults },
};

/** Many chips to test flex wrap behavior. */
export const ManyChips: Story = {
  args: { blocks: manyBlocks, toolResultMap: manyResults },
};

/** All chips executing (no results yet). */
export const AllExecuting: Story = {
  args: {
    blocks: multiBlocks,
    toolResultMap: new Map(),
    inProgressMessageId: "msg-active",
  },
};
