import type { Meta, StoryObj } from "@storybook/react-vite";
import { createStore, Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { ToolResultBlock, ToolUseBlock, Workspace } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces";
import { chatToolDensityAtom } from "~/pages/workspace/chat/atoms/chat.ts";
import { ToolPillRow } from "~/pages/workspace/chat/ToolPillRow.tsx";

import { toolResult, toolUse } from "./fixtures/tools.ts";

const STORYBOOK_WORKSPACE_ID = "storybook-ws";
// `useWorkspaceCodePath` returns `${environmentId}/code` for CLONE workspaces,
// so the resolved prefix is `/Users/dev/work/sculptor-env/code`.
const WORKSPACE_CODE_PATH_PREFIX = "/Users/dev/work/sculptor-env/code";

const STORYBOOK_WORKSPACE: Workspace = {
  objectId: STORYBOOK_WORKSPACE_ID,
  projectId: "storybook-project",
  organizationReference: "storybook-org",
  description: "Storybook fixture",
  initializationStrategy: WorkspaceInitializationStrategy.CLONE,
  environmentId: "/Users/dev/work/sculptor-env",
};

const seedWorkspaceStore = (density: "default" | "expanded" = "default"): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(workspaceAtomFamily(STORYBOOK_WORKSPACE_ID), STORYBOOK_WORKSPACE);
  store.set(chatToolDensityAtom, density);
  return store;
};

const readBlock = toolUse("pr-001", "Read", { file_path: "src/utils/fetch.ts" });
const bashBlock = toolUse("pr-002", "Bash", { command: "npm test" });
const grepBlock = toolUse("pr-003", "Grep", { pattern: "useEffect" });
const globBlock = toolUse("pr-004", "Glob", { pattern: "**/*.test.ts" });
const read2Block = toolUse("pr-005", "Read", { file_path: "src/index.ts" });

const readRes = toolResult("pr-001", "Read", "function fetchData() {}");
const bashRes = toolResult("pr-002", "Bash", "All 42 tests passed.");
const grepRes = toolResult("pr-003", "Grep", "src/Button.tsx:12\nsrc/Home.tsx:34");
const globRes = toolResult("pr-004", "Glob", "src/__tests__/a.test.ts\nsrc/__tests__/b.test.ts");
const read2Res = toolResult("pr-005", "Read", 'import "./app";');

const allBlocks: ReadonlyArray<ToolUseBlock | ToolResultBlock> = [
  readBlock,
  bashBlock,
  grepBlock,
  globBlock,
  read2Block,
];

const allResults = new Map<string, ToolResultBlock>([
  [readBlock.id, readRes],
  [bashBlock.id, bashRes],
  [grepBlock.id, grepRes],
  [globBlock.id, globRes],
  [read2Block.id, read2Res],
]);

const partialResults = new Map<string, ToolResultBlock>([
  [readBlock.id, readRes],
  [bashBlock.id, bashRes],
]);

const errorResults = new Map<string, ToolResultBlock>([
  [readBlock.id, readRes],
  [bashBlock.id, toolResult("pr-002", "Bash", "FAIL: fetch is not defined", true)],
]);

// Mixed in-/outside-workspace fixture demonstrating the `folder-output` icon
// indicator inside the accordion popover. Inside paths sit under
// `WORKSPACE_CODE_PATH_PREFIX` and get stripped to a project-relative form.
// Outside paths retain their full absolute form and get flagged with the icon.

const inside = (p: string): string => `${WORKSPACE_CODE_PATH_PREFIX}/${p}`;

const mixedReadInsideA = toolUse("mx-r1", "Read", { file_path: inside("src/components/Button.tsx") });
const mixedReadInsideB = toolUse("mx-r2", "Read", { file_path: inside("src/utils/fetch.ts") });
const mixedReadInsideC = toolUse("mx-r3", "Read", { file_path: inside("src/hooks/useAuth.ts") });
const mixedReadOutsideA = toolUse("mx-r4", "Read", {
  file_path: "/Users/dev/.config/sculptor/settings.json",
});
const mixedReadInsideD = toolUse("mx-r5", "Read", { file_path: inside("src/pages/Home.tsx") });
const mixedReadOutsideB = toolUse("mx-r6", "Read", {
  file_path: "/Users/dev/Library/Application Support/sculptor/cache/data.json",
});
const mixedReadInsideE = toolUse("mx-r7", "Read", { file_path: inside("src/index.ts") });

const mixedGrepOutside = toolUse("mx-g1", "Grep", {
  pattern: "useEffect",
  path: "/Users/dev/work/other-project/src",
});
const mixedBash = toolUse("mx-b1", "Bash", { command: "npm test" });

const mixedBlocks: ReadonlyArray<ToolUseBlock | ToolResultBlock> = [
  mixedReadInsideA,
  mixedReadInsideB,
  mixedReadInsideC,
  mixedReadOutsideA,
  mixedReadInsideD,
  mixedReadOutsideB,
  mixedReadInsideE,
  mixedGrepOutside,
  mixedBash,
];

const mixedResults = new Map<string, ToolResultBlock>([
  [mixedReadInsideA.id, toolResult("mx-r1", "Read", "export const Button = () => null;")],
  [mixedReadInsideB.id, toolResult("mx-r2", "Read", "export async function fetchData() {}")],
  [mixedReadInsideC.id, toolResult("mx-r3", "Read", "export const useAuth = () => ({});")],
  [mixedReadOutsideA.id, toolResult("mx-r4", "Read", '{ "theme": "dark" }')],
  [mixedReadInsideD.id, toolResult("mx-r5", "Read", "export default function Home() {}")],
  [mixedReadOutsideB.id, toolResult("mx-r6", "Read", '{"cached":true}')],
  [mixedReadInsideE.id, toolResult("mx-r7", "Read", 'import "./app";')],
  [
    mixedGrepOutside.id,
    toolResult("mx-g1", "Grep", "src/components/Button.tsx:12\nsrc/pages/Home.tsx:34\nsrc/hooks/useAuth.ts:8"),
  ],
  [mixedBash.id, toolResult("mx-b1", "Bash", "All 42 tests passed.")],
]);

const meta = {
  title: "Chat/Tools/ToolPillRow",
  decorators: [
    (Story): ReactElement => (
      <JotaiProvider store={seedWorkspaceStore()}>
        <MemoryRouter initialEntries={[`/ws/${STORYBOOK_WORKSPACE_ID}/agent/storybook-agent`]}>
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
      </JotaiProvider>
    ),
  ],
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

/** Single completed tool. */
export const SingleTool: Story = {
  render: (): ReactElement => (
    <ToolPillRow blocks={[readBlock]} toolResultMap={new Map([[readBlock.id, readRes]])} inProgressMessageId={null} />
  ),
};

/** Multiple completed tools in summary mode. */
export const MultipleCompleted: Story = {
  render: (): ReactElement => <ToolPillRow blocks={allBlocks} toolResultMap={allResults} inProgressMessageId={null} />,
};

/** Some tools still executing. */
export const PartiallyExecuting: Story = {
  render: (): ReactElement => (
    <ToolPillRow blocks={allBlocks} toolResultMap={partialResults} inProgressMessageId="msg-active" />
  ),
};

/** All tools still executing. */
export const AllExecuting: Story = {
  render: (): ReactElement => (
    <ToolPillRow blocks={allBlocks} toolResultMap={new Map()} inProgressMessageId="msg-active" />
  ),
};

/** One tool errored. */
export const WithError: Story = {
  render: (): ReactElement => (
    <ToolPillRow blocks={[readBlock, bashBlock]} toolResultMap={errorResults} inProgressMessageId={null} />
  ),
};

/**
 * Group of tools with a mix of in- and outside-workspace paths. The seeded
 * workspace makes `useWorkspaceCodePath` resolve to a real prefix, so inside
 * paths get stripped to a project-relative form and outside paths keep their
 * full absolute form with the `folder-output` icon. Click the pill to expand
 * the popover.
 */
export const MixedWorkspacePaths: Story = {
  render: (): ReactElement => (
    <ToolPillRow blocks={mixedBlocks} toolResultMap={mixedResults} inProgressMessageId={null} />
  ),
};

/**
 * A bash command long enough that the popover's command section scrolls.
 * Verifies the description stays pinned in the header above the command
 * rather than scrolling out of view at the bottom.
 */
const LONG_BASH_COMMAND = [
  "ls /Users/dev/cache/sculptor-mr-testing/.dev_sculptor/workspaces/cbda9243ebbb49bf84598e8f78929ae1/code/sculptor/frontend/src/pages",
  "/Users/dev/cache/sculptor-mr-testing/.dev_sculptor/workspaces/cbda9243ebbb49bf84598e8f78929ae1/code/sculptor/frontend/src/hooks",
  "/Users/dev/cache/sculptor-mr-testing/.dev_sculptor/workspaces/cbda9243ebbb49bf84598e8f78929ae1/code/sculptor/frontend/src/components",
  "2>/dev/null | head -100",
].join(" ");
const longBashBlock = toolUse("ls-001", "Bash", {
  command: LONG_BASH_COMMAND,
  description: "List subdirs of frontend",
});
const longBashRes = toolResult("ls-001", "Bash", "src/pages/Home.tsx\nsrc/pages/Settings.tsx\nsrc/hooks/useAuth.ts");

export const LongBashWithDescription: Story = {
  render: (): ReactElement => (
    <ToolPillRow
      blocks={[longBashBlock]}
      toolResultMap={new Map([[longBashBlock.id, longBashRes]])}
      inProgressMessageId={null}
    />
  ),
};

/**
 * Expanded chat tool density (Cmd+K → "Expand tool calls"). Each call
 * gets its own row with the tool name leading and the popover-header
 * content (file path / pattern / command, plus meta and actions) inlined.
 * The popover itself is unchanged — clicking still opens it.
 */
export const ExpandedDensity: Story = {
  decorators: [
    (Story): ReactElement => (
      <JotaiProvider store={seedWorkspaceStore("expanded")}>
        <MemoryRouter initialEntries={[`/ws/${STORYBOOK_WORKSPACE_ID}/agent/storybook-agent`]}>
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
      </JotaiProvider>
    ),
  ],
  render: (): ReactElement => (
    <ToolPillRow blocks={mixedBlocks} toolResultMap={mixedResults} inProgressMessageId={null} />
  ),
};
