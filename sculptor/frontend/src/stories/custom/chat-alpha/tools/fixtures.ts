/**
 * Shared mock data for subagent stories.
 *
 * Provides pre-built ToolUseBlock / ToolResultBlock / PillData / SubagentTreeNode
 * fixtures so each story file can import what it needs without duplicating builders.
 */

import type { ChatMessage, ToolResultBlock, ToolUseBlock } from "~/api";
import { ChatMessageRole } from "~/api";
import type { PillData } from "~/pages/workspace/components/chat-alpha/toolPill.types.ts";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";

let fixtureIdCounter = 0;

// ---------------------------------------------------------------------------
// Low-level block builders (same pattern as AlphaChipRow.stories)
// ---------------------------------------------------------------------------

export const toolUse = (id: string, name: string, input: Record<string, unknown> = {}): ToolUseBlock =>
  ({ type: "tool_use", id, name, input }) as unknown as ToolUseBlock;

export const toolResult = (toolUseId: string, toolName: string, text: string, isError = false): ToolResultBlock =>
  ({
    type: "tool_result",
    toolUseId,
    toolName,
    invocationString: `${toolName}(...)`,
    content: { contentType: "generic", text },
    isError,
  }) as unknown as ToolResultBlock;

// ---------------------------------------------------------------------------
// PillData fixtures — only tools that render as pills (not Bash/Edit/Write)
// ---------------------------------------------------------------------------

export const completedReadPill: PillData = {
  id: "tu-001",
  label: "Read",
  state: "completed",
  blocks: [toolUse("tu-001", "Read", { file_path: "src/utils/fetch.ts" })],
  results: [
    toolResult(
      "tu-001",
      "Read",
      'function fetchData(callback) {\n  http.get("/api/data", (res) => {\n    callback(null, res);\n  });\n}',
    ),
  ],
};

export const completedGrepPill: PillData = {
  id: "tu-003",
  label: "Grep",
  state: "completed",
  blocks: [toolUse("tu-003", "Grep", { pattern: "useEffect", path: "src/" })],
  results: [
    toolResult("tu-003", "Grep", "src/components/Button.tsx:12\nsrc/pages/Home.tsx:34\nsrc/hooks/useAuth.ts:8"),
  ],
};

export const completedGlobPill: PillData = {
  id: "tu-030",
  label: "Glob",
  state: "completed",
  blocks: [toolUse("tu-030", "Glob", { pattern: "src/**/*.test.ts" })],
  results: [
    toolResult(
      "tu-030",
      "Glob",
      "src/__tests__/Button.test.ts\nsrc/__tests__/fetch.test.ts\nsrc/__tests__/auth.test.ts\nsrc/__tests__/utils.test.ts",
    ),
  ],
};

export const completedLsPill: PillData = {
  id: "tu-031",
  label: "LS",
  state: "completed",
  blocks: [toolUse("tu-031", "LS", { file_path: "src/components" })],
  results: [toolResult("tu-031", "LS", "Button.tsx\nHeader.tsx\nFooter.tsx\nSidebar.tsx\nindex.ts")],
};

export const completedWebFetchPill: PillData = {
  id: "tu-032",
  label: "WebFetch",
  state: "completed",
  blocks: [toolUse("tu-032", "WebFetch", { url: "https://docs.example.com/api/v2/reference" })],
  results: [toolResult("tu-032", "WebFetch", "<!DOCTYPE html>\n<html><body><h1>API Reference</h1>...</body></html>")],
};

export const completedWebSearchPill: PillData = {
  id: "tu-033",
  label: "WebSearch",
  state: "completed",
  blocks: [toolUse("tu-033", "WebSearch", { query: "react useEffect cleanup pattern" })],
  results: [
    toolResult(
      "tu-033",
      "WebSearch",
      "1. React docs — Synchronizing with Effects\n2. Stack Overflow — useEffect cleanup\n3. Blog — Common useEffect mistakes",
    ),
  ],
};

export const completedSkillPill: PillData = {
  id: "tu-034",
  label: "Skill",
  state: "completed",
  blocks: [toolUse("tu-034", "Skill", { skill: "commit" })],
  results: [toolResult("tu-034", "Skill", "Skill 'commit' executed successfully.")],
};

export const completedReadOutsideWorkspacePill: PillData = {
  id: "tu-040",
  label: "Read",
  state: "completed",
  blocks: [toolUse("tu-040", "Read", { file_path: "/Users/dev/work/other-project/src/utils/fetch.ts" })],
  results: [
    toolResult(
      "tu-040",
      "Read",
      'function fetchData(callback) {\n  http.get("/api/data", (res) => {\n    callback(null, res);\n  });\n}',
    ),
  ],
};

export const completedGrepOutsideWorkspacePill: PillData = {
  id: "tu-041",
  label: "Grep",
  state: "completed",
  blocks: [
    toolUse("tu-041", "Grep", {
      pattern: "useEffect",
      path: "/Users/dev/work/other-project/src",
    }),
  ],
  results: [
    toolResult("tu-041", "Grep", "src/components/Button.tsx:12\nsrc/pages/Home.tsx:34\nsrc/hooks/useAuth.ts:8"),
  ],
};

export const completedNotebookReadPill: PillData = {
  id: "tu-035",
  label: "NotebookRead",
  state: "completed",
  blocks: [toolUse("tu-035", "NotebookRead", { file_path: "notebooks/analysis.ipynb" })],
  results: [
    toolResult(
      "tu-035",
      "NotebookRead",
      "Cell 1 [code]: import pandas as pd\nCell 2 [code]: df = pd.read_csv('data.csv')\nCell 3 [markdown]: ## Results",
    ),
  ],
};

export const executingGrepPill: PillData = {
  id: "tu-010",
  label: "Grep",
  state: "initializing",
  blocks: [toolUse("tu-010", "Grep", { pattern: "handleSubmit", path: "src/" })],
  results: [],
};

export const errorReadPill: PillData = {
  id: "tu-020",
  label: "Read",
  state: "error",
  blocks: [toolUse("tu-020", "Read", { file_path: "src/missing-file.ts" })],
  results: [toolResult("tu-020", "Read", "Error: ENOENT: no such file or directory", true)],
};

// ---------------------------------------------------------------------------
// Subagent tree node helpers
// ---------------------------------------------------------------------------

const chatMessage = (
  content: ReadonlyArray<Record<string, unknown>>,
  role: ChatMessageRole = ChatMessageRole.ASSISTANT,
): ChatMessage =>
  ({
    role,
    id: `msg-${fixtureIdCounter++}`,
    content,
    approximateCreationTime: new Date().toISOString(),
  }) as unknown as ChatMessage;

export const makeSubagentTreeNodes = (
  parentToolUseId: string,
  toolBlocks: Array<{ use: ToolUseBlock; result?: ToolResultBlock }>,
): Array<SubagentTreeNode> =>
  toolBlocks.map(({ use, result }) => ({
    message: chatMessage(result ? [use, result] : [use]),
    children: new Map(),
  }));

// ---------------------------------------------------------------------------
// Pre-built subagent scenarios
// ---------------------------------------------------------------------------

const parentBlock = toolUse("agent-001", "Agent", {
  description: "Explore repo structure",
  prompt: "Search the repository for test configuration files and summarize the testing setup.",
});

const readBlock = toolUse("sub-001", "Read", { file_path: "jest.config.ts" });
const readResult = toolResult("sub-001", "Read", 'module.exports = { preset: "ts-jest" };');
const grepBlock = toolUse("sub-002", "Grep", { pattern: "describe\\(" });
const grepResult = toolResult("sub-002", "Grep", "src/__tests__/Button.test.tsx:5\nsrc/__tests__/fetch.test.ts:3");
const bashBlock = toolUse("sub-003", "Bash", { command: "npx jest --listTests" });
const bashResult = toolResult("sub-003", "Bash", "Found 12 test files.");

export const completedSubagent = {
  parentBlock,
  childNodes: makeSubagentTreeNodes(parentBlock.id, [
    { use: readBlock, result: readResult },
    { use: grepBlock, result: grepResult },
    { use: bashBlock, result: bashResult },
  ]),
  toolResultMap: new Map<string, ToolResultBlock>([
    [readBlock.id, readResult],
    [grepBlock.id, grepResult],
    [bashBlock.id, bashResult],
  ]),
  metadata: new Map<string, SubagentMetadata>([
    [
      parentBlock.id,
      {
        subagentType: "Explore",
        prompt: "Search the repository for test configuration files and summarize the testing setup.",
        responseText:
          "The project uses **Jest** with `ts-jest` preset. I found 12 test files across `src/__tests__/`. " +
          "The configuration lives in `jest.config.ts` at the repo root.",
      },
    ],
  ]),
};

const thinkingParent = toolUse("agent-002", "Agent", {
  description: "Fix failing tests",
  prompt: "Investigate why the test suite is failing and propose a fix.",
});

export const thinkingSubagent = {
  parentBlock: thinkingParent,
  childNodes: makeSubagentTreeNodes(thinkingParent.id, [{ use: readBlock }]),
  toolResultMap: new Map<string, ToolResultBlock>(),
  metadata: new Map<string, SubagentMetadata>([
    [
      thinkingParent.id,
      {
        subagentType: "general-purpose",
        prompt: "Investigate why the test suite is failing and propose a fix.",
      },
    ],
  ]),
};

const noToolsParent = toolUse("agent-003", "Agent", {
  description: "Answer question",
  prompt: "What testing framework does this project use?",
});

export const noToolsSubagent = {
  parentBlock: noToolsParent,
  childNodes: [] as Array<SubagentTreeNode>,
  toolResultMap: new Map<string, ToolResultBlock>(),
  metadata: new Map<string, SubagentMetadata>([
    [
      noToolsParent.id,
      {
        subagentType: "Explore",
        prompt: "What testing framework does this project use?",
        responseText: "The project uses Jest with TypeScript support via ts-jest.",
      },
    ],
  ]),
};

// ---------------------------------------------------------------------------
// Background subagent scenarios (run_in_background: true)
// ---------------------------------------------------------------------------

const bgCompletedParent = toolUse("agent-bg-001", "Agent", {
  description: "Explore repo structure",
  prompt: "Search the repository for test configuration files and summarize the testing setup.",
  run_in_background: true,
});

const bgReadBlock = toolUse("sub-bg-001", "Read", { file_path: "jest.config.ts" });
const bgReadResult = toolResult("sub-bg-001", "Read", 'module.exports = { preset: "ts-jest" };');

export const backgroundCompletedSubagent = {
  parentBlock: bgCompletedParent,
  childNodes: makeSubagentTreeNodes(bgCompletedParent.id, [{ use: bgReadBlock, result: bgReadResult }]),
  toolResultMap: new Map<string, ToolResultBlock>([[bgReadBlock.id, bgReadResult]]),
  metadata: new Map<string, SubagentMetadata>([
    [
      bgCompletedParent.id,
      {
        subagentType: "Explore",
        prompt: "Search the repository for test configuration files and summarize the testing setup.",
        responseText: "The project uses Jest with ts-jest preset. Configuration is in jest.config.ts.",
      },
    ],
  ]),
};

const bgThinkingParent = toolUse("agent-bg-002", "Agent", {
  description: "Fix failing tests",
  prompt: "Investigate why the test suite is failing and propose a fix.",
  run_in_background: true,
});

export const backgroundThinkingSubagent = {
  parentBlock: bgThinkingParent,
  childNodes: makeSubagentTreeNodes(bgThinkingParent.id, [{ use: bgReadBlock }]),
  toolResultMap: new Map<string, ToolResultBlock>(),
  metadata: new Map<string, SubagentMetadata>([
    [
      bgThinkingParent.id,
      {
        subagentType: "general-purpose",
        prompt: "Investigate why the test suite is failing and propose a fix.",
      },
    ],
  ]),
};
