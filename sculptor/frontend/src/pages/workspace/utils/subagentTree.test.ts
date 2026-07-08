import { describe, expect, it } from "vitest";

import type { ChatMessage } from "../../../api";
import {
  buildSubagentMetadataMap,
  buildSubagentTree,
  extractTextFromToolContent,
  getToolUseId,
  hasVisibleToolContent,
} from "./subagentTree.ts";

const makeMessage = (id: string, content: ChatMessage["content"], parentToolUseId?: string): ChatMessage =>
  ({
    id,
    role: "assistant",
    content,
    parentToolUseId: parentToolUseId ?? null,
    approximateCreationTime: new Date().toISOString(),
  }) as unknown as ChatMessage;

const makeToolUse = (
  id: string,
  name: string,
  input?: Record<string, unknown>,
): { type: "tool_use"; id: string; name: string; input: Record<string, unknown> } => ({
  type: "tool_use" as const,
  id,
  name,
  input: input ?? {},
});

const makeToolResult = (
  toolUseId: string,
  toolName: string,
  text?: string,
  backgroundTaskId?: string,
): {
  type: "tool_result";
  toolUseId: string;
  toolName: string;
  invocationString: string;
  isError: boolean;
  content: { contentType: "generic"; text: string };
  backgroundTaskId?: string;
} => ({
  type: "tool_result" as const,
  toolUseId,
  toolName,
  invocationString: "",
  isError: false,
  content: text ? { contentType: "generic", text } : { contentType: "generic", text: "" },
  ...(backgroundTaskId !== undefined ? { backgroundTaskId } : {}),
});

const makeTextBlock = (text: string): { type: "text"; text: string } => ({
  type: "text" as const,
  text,
});

describe("getToolUseId", () => {
  it("returns id for tool_use blocks", () => {
    expect(getToolUseId(makeToolUse("tu_1", "Bash"))).toBe("tu_1");
  });

  it("returns toolUseId for tool_result blocks", () => {
    expect(getToolUseId(makeToolResult("tu_1", "Bash"))).toBe("tu_1");
  });

  it("returns undefined for text blocks", () => {
    expect(getToolUseId(makeTextBlock("hello"))).toBeUndefined();
  });
});

describe("buildSubagentTree", () => {
  it("returns all messages as top-level when none have parentToolUseId", () => {
    const messages = [makeMessage("m1", [makeTextBlock("hello")]), makeMessage("m2", [makeToolUse("tu_1", "Bash")])];
    const tree = buildSubagentTree(messages);
    expect(tree).toHaveLength(2);
    expect(tree[0].message.id).toBe("m1");
    expect(tree[1].message.id).toBe("m2");
    expect(tree[0].children.size).toBe(0);
    expect(tree[1].children.size).toBe(0);
  });

  it("nests child messages under the parent tool_use block", () => {
    const messages = [
      makeMessage("m1", [makeToolUse("tu_task", "Task")]),
      makeMessage("m2", [makeToolUse("tu_bash", "Bash")], "tu_task"),
    ];
    const tree = buildSubagentTree(messages);
    expect(tree).toHaveLength(1);
    expect(tree[0].children.size).toBe(1);
    const children = tree[0].children.get("tu_task")!;
    expect(children).toHaveLength(1);
    expect(children[0].message.id).toBe("m2");
  });

  it("supports multiple children under the same parent", () => {
    const messages = [
      makeMessage("m1", [makeToolUse("tu_task", "Task")]),
      makeMessage("c1", [makeToolUse("tu_b1", "Bash")], "tu_task"),
      makeMessage("c2", [makeToolUse("tu_b2", "Read")], "tu_task"),
    ];
    const tree = buildSubagentTree(messages);
    expect(tree).toHaveLength(1);
    const children = tree[0].children.get("tu_task")!;
    expect(children).toHaveLength(2);
  });

  it("supports multi-level nesting (sub-subagents)", () => {
    const messages = [
      makeMessage("m1", [makeToolUse("tu_task1", "Task")]),
      makeMessage("c1", [makeToolUse("tu_task2", "Task")], "tu_task1"),
      makeMessage("gc1", [makeToolUse("tu_bash", "Bash")], "tu_task2"),
    ];
    const tree = buildSubagentTree(messages);
    expect(tree).toHaveLength(1);
    const level1 = tree[0].children.get("tu_task1")!;
    expect(level1).toHaveLength(1);
    const level2 = level1[0].children.get("tu_task2")!;
    expect(level2).toHaveLength(1);
    expect(level2[0].message.id).toBe("gc1");
  });

  it("attaches children via tool_result blocks too", () => {
    const messages = [
      makeMessage("m1", [makeToolResult("tu_task", "Task")]),
      makeMessage("c1", [makeToolUse("tu_bash", "Bash")], "tu_task"),
    ];
    const tree = buildSubagentTree(messages);
    expect(tree).toHaveLength(1);
    expect(tree[0].children.get("tu_task")).toHaveLength(1);
  });
});

describe("extractTextFromToolContent", () => {
  it("extracts text from simple single-quoted Python repr", () => {
    const raw = "[{'type': 'text', 'text': 'Simple response text here.'}]";
    expect(extractTextFromToolContent(raw)).toBe("Simple response text here.");
  });

  it("extracts text from double-quoted Python repr (apostrophes in text)", () => {
    const raw = `[{'type': 'text', 'text': "It's working well and the agent's output is correct."}]`;
    expect(extractTextFromToolContent(raw)).toBe("It's working well and the agent's output is correct.");
  });

  it("joins multiple text blocks", () => {
    const raw = "[{'type': 'text', 'text': 'First part. '}, {'type': 'text', 'text': 'Second part.'}]";
    expect(extractTextFromToolContent(raw)).toBe("First part. Second part.");
  });

  it("filters out agentId metadata blocks", () => {
    const raw = "[{'type': 'text', 'text': 'Good response'}, {'type': 'text', 'text': 'agentId: a73e48b'}]";
    expect(extractTextFromToolContent(raw)).toBe("Good response");
  });

  it("handles escaped apostrophes in single-quoted strings", () => {
    const raw = `[{'type': 'text', 'text': 'It\\'s a "test"'}]`;
    expect(extractTextFromToolContent(raw)).toBe('It\'s a "test"');
  });

  it("handles escaped newlines", () => {
    const raw = "[{'type': 'text', 'text': 'Line 1\\nLine 2\\nLine 3'}]";
    expect(extractTextFromToolContent(raw)).toBe("Line 1\nLine 2\nLine 3");
  });

  it("returns raw string when pattern does not match", () => {
    const raw = "Just a plain string response";
    expect(extractTextFromToolContent(raw)).toBe("Just a plain string response");
  });
});

describe("buildSubagentMetadataMap", () => {
  it("extracts subagent type and prompt from Task tool_use blocks", () => {
    const messages = [
      {
        content: [makeToolUse("tu_1", "Task", { subagent_type: "Explore", prompt: "Find the file" })],
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    expect(map.size).toBe(1);
    const meta = map.get("tu_1")!;
    expect(meta.subagentType).toBe("Explore");
    expect(meta.prompt).toBe("Find the file");
    expect(meta.responseText).toBeUndefined();
  });

  it("extracts subagent type and prompt from Agent tool_use blocks", () => {
    const messages = [
      {
        content: [makeToolUse("tu_1", "Agent", { subagent_type: "Explore", prompt: "Find the file" })],
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    expect(map.size).toBe(1);
    const meta = map.get("tu_1")!;
    expect(meta.subagentType).toBe("Explore");
    expect(meta.prompt).toBe("Find the file");
    expect(meta.responseText).toBeUndefined();
  });

  it("extracts response text from matching tool_result blocks", () => {
    const messages = [
      {
        content: [
          makeToolUse("tu_1", "Task", { subagent_type: "Explore", prompt: "Find it" }),
          makeToolResult("tu_1", "Task", "[{'type': 'text', 'text': 'Found it!'}]"),
        ],
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    expect(map.get("tu_1")!.responseText).toBe("Found it!");
  });

  it("extracts response text from Agent tool_result blocks", () => {
    const messages = [
      {
        content: [
          makeToolUse("tu_1", "Agent", { subagent_type: "Explore", prompt: "Find it" }),
          makeToolResult("tu_1", "Agent", "[{'type': 'text', 'text': 'Found it!'}]"),
        ],
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    expect(map.get("tu_1")!.responseText).toBe("Found it!");
  });

  it("ignores non-Task tool_use blocks", () => {
    const messages = [{ content: [makeToolUse("tu_1", "Bash", {})] }];
    const map = buildSubagentMetadataMap(messages);
    expect(map.size).toBe(0);
  });

  // SCU-1151: background subagents emit an immediate launch-ack tool_result
  // ("Async agent launched successfully.\nagentId: ...") right after the Agent
  // tool_use. That text is internal book-keeping — it must not surface in the
  // UI as the subagent's response.
  it("does not capture the launch-ack tool_result as responseText for background agents", () => {
    const messages = [
      {
        content: [
          makeToolUse("tu_bg", "Agent", {
            subagent_type: "general-purpose",
            prompt: "List all Python files",
            run_in_background: true,
          }),
          makeToolResult("tu_bg", "Agent", "Async agent launched successfully.\nagentId: msg_abc123"),
        ],
        parentToolUseId: null,
        approximateCreationTime: "2026-05-18T19:00:00Z",
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    const meta = map.get("tu_bg")!;
    expect(meta.prompt).toBe("List all Python files");
    expect(meta.isBackground).toBe(true);
    // The launch-ack text MUST NOT leak into responseText.
    expect(meta.responseText).toBeUndefined();
  });

  it("derives responseText for background agents from the subagent's child messages", () => {
    const messages = [
      {
        // Main agent message: text + Agent tool_use + launch-ack tool_result.
        content: [
          { type: "text", text: "I'll use a background subagent to help with this." },
          makeToolUse("tu_bg", "Agent", {
            subagent_type: "general-purpose",
            prompt: "List all Python files",
            run_in_background: true,
          }),
          makeToolResult("tu_bg", "Agent", "Async agent launched successfully.\nagentId: sub_msg"),
        ],
        parentToolUseId: null,
        approximateCreationTime: "2026-05-18T19:00:00Z",
      },
      {
        // Subagent's actual response — child of the Agent tool_use.
        content: [{ type: "text", text: "Found 42 Python files in the repository." }],
        parentToolUseId: "tu_bg",
        approximateCreationTime: "2026-05-18T19:00:15Z",
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    const meta = map.get("tu_bg")!;
    expect(meta.isBackground).toBe(true);
    expect(meta.responseText).toBe("Found 42 Python files in the repository.");
    // 15s between the Agent tool_use message and the subagent's reply.
    expect(meta.durationSeconds).toBeCloseTo(15, 0);
  });

  it("picks the latest-by-timestamp child message as the background subagent's response", () => {
    // Streaming/reconnect-replay can deliver child messages in non-chronological
    // order. The newest reply should win regardless of array order.
    const messages = [
      {
        content: [
          makeToolUse("tu_bg", "Agent", { prompt: "Find files", run_in_background: true }),
          makeToolResult("tu_bg", "Agent", "Async agent launched successfully.\nagentId: sub_msg"),
        ],
        parentToolUseId: null,
        approximateCreationTime: "2026-05-18T19:00:00Z",
      },
      // Later-arriving but chronologically earlier partial reply.
      {
        content: [{ type: "text", text: "Working on it..." }],
        parentToolUseId: "tu_bg",
        approximateCreationTime: "2026-05-18T19:00:05Z",
      },
      // Final reply (latest by timestamp).
      {
        content: [{ type: "text", text: "Final answer." }],
        parentToolUseId: "tu_bg",
        approximateCreationTime: "2026-05-18T19:00:20Z",
      },
      // Late-arriving partial — older timestamp, must NOT clobber the final.
      {
        content: [{ type: "text", text: "Stale partial." }],
        parentToolUseId: "tu_bg",
        approximateCreationTime: "2026-05-18T19:00:10Z",
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    const meta = map.get("tu_bg")!;
    expect(meta.responseText).toBe("Final answer.");
    expect(meta.durationSeconds).toBeCloseTo(20, 0);
  });

  it("marks Agent tool_use as background when run_in_background is set, otherwise not", () => {
    const messages = [
      {
        content: [
          makeToolUse("tu_fg", "Agent", { prompt: "Foreground" }),
          makeToolUse("tu_bg", "Agent", { prompt: "Background", run_in_background: true }),
        ],
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    expect(map.get("tu_fg")!.isBackground).toBeFalsy();
    expect(map.get("tu_bg")!.isBackground).toBe(true);
  });

  // SCU-1792: an Agent call the harness converts to an async agent has NO
  // run_in_background in its input — the only signal is the backgroundTaskId
  // the backend stamps on the launch-ack tool_result. Without it the ack text
  // ("Async agent launched... internal ID - do not mention to user...") leaks
  // into the popover as the Response and the pill freezes at ~0.0s.
  it("treats a harness-converted agent (backgroundTaskId stamp, no input flag) as background", () => {
    const messages = [
      {
        content: [
          makeToolUse("tu_conv", "Agent", { subagent_type: "Explore", prompt: "Investigate the repo" }),
          makeToolResult("tu_conv", "Agent", "Async agent launched successfully.\nagentId: abc123", "task-1"),
        ],
        parentToolUseId: null,
        approximateCreationTime: "2026-07-08T12:00:00Z",
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    const meta = map.get("tu_conv")!;
    expect(meta.isBackground).toBe(true);
    expect(meta.backgroundTaskId).toBe("task-1");
    expect(meta.responseText).toBeUndefined();
  });

  it("derives responseText and duration for a converted agent from its child messages", () => {
    const messages = [
      {
        content: [
          makeToolUse("tu_conv", "Agent", { prompt: "Investigate" }),
          makeToolResult("tu_conv", "Agent", "Async agent launched successfully.", "task-1"),
        ],
        parentToolUseId: null,
        approximateCreationTime: "2026-07-08T12:00:00Z",
      },
      {
        content: [{ type: "text", text: "Investigation complete." }],
        parentToolUseId: "tu_conv",
        approximateCreationTime: "2026-07-08T12:02:00Z",
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    const meta = map.get("tu_conv")!;
    expect(meta.responseText).toBe("Investigation complete.");
    expect(meta.durationSeconds).toBeCloseTo(120, 0);
  });

  it("computes stillRunning from the pending background task set", () => {
    const makeConverted = (
      toolUseId: string,
      taskId: string,
    ): { content: Array<Record<string, unknown>>; parentToolUseId: null; approximateCreationTime: string } => ({
      content: [
        makeToolUse(toolUseId, "Agent", { prompt: "Work" }),
        makeToolResult(toolUseId, "Agent", "Async agent launched successfully.", taskId),
      ],
      parentToolUseId: null,
      approximateCreationTime: "2026-07-08T12:00:00Z",
    });
    const messages = [
      makeConverted("tu_running", "task-running"),
      makeConverted("tu_lost", "task-lost"),
      makeConverted("tu_done", "task-done"),
      {
        content: [{ type: "text", text: "Done." }],
        parentToolUseId: "tu_done",
        approximateCreationTime: "2026-07-08T12:01:00Z",
      },
    ];
    const map = buildSubagentMetadataMap(messages, new Set(["task-running"]));
    // Still in the pending set: running, keep the live timer ticking.
    expect(map.get("tu_running")!.stillRunning).toBe(true);
    // Left the pending set without a response child (orphaned completion):
    // the timer must settle rather than tick forever.
    expect(map.get("tu_lost")!.stillRunning).toBe(false);
    // Response arrived: liveness is moot, leave it unset.
    expect(map.get("tu_done")!.stillRunning).toBeUndefined();
  });

  it("leaves stillRunning unset when the pending set is not provided", () => {
    const messages = [
      {
        content: [
          makeToolUse("tu_conv", "Agent", { prompt: "Work" }),
          makeToolResult("tu_conv", "Agent", "Async agent launched successfully.", "task-1"),
        ],
        parentToolUseId: null,
        approximateCreationTime: "2026-07-08T12:00:00Z",
      },
    ];
    const map = buildSubagentMetadataMap(messages);
    expect(map.get("tu_conv")!.stillRunning).toBeUndefined();
  });
});

describe("hasVisibleToolContent", () => {
  it("returns true for text-only blocks (no subagent tools)", () => {
    expect(hasVisibleToolContent([makeTextBlock("hello")] as never)).toBe(true);
  });

  it("returns true for tool blocks without subagent children", () => {
    const blocks = [makeToolUse("tu_1", "Bash")] as never;
    expect(hasVisibleToolContent(blocks, new Map())).toBe(true);
  });

  it("returns false when all blocks are subagent parents", () => {
    const childNodes = [{ message: makeMessage("c1", []), children: new Map() }];
    const subagentChildren = new Map([["tu_1", childNodes]]);
    const blocks = [makeToolUse("tu_1", "Task")] as never;
    expect(hasVisibleToolContent(blocks, subagentChildren)).toBe(false);
  });

  it("returns false when message has text plus subagent tool blocks only", () => {
    const childNodes = [{ message: makeMessage("c1", []), children: new Map() }];
    const subagentChildren = new Map([["tu_1", childNodes]]);
    const blocks = [makeTextBlock("Let me investigate..."), makeToolUse("tu_1", "Task")] as never;
    expect(hasVisibleToolContent(blocks, subagentChildren)).toBe(false);
  });

  it("returns true when message has text plus a mix of subagent and regular tools", () => {
    const childNodes = [{ message: makeMessage("c1", []), children: new Map() }];
    const subagentChildren = new Map([["tu_1", childNodes]]);
    const blocks = [
      makeTextBlock("Let me investigate..."),
      makeToolUse("tu_1", "Task"),
      makeToolUse("tu_2", "Bash"),
    ] as never;
    expect(hasVisibleToolContent(blocks, subagentChildren)).toBe(true);
  });

  it("returns true when some blocks are subagent parents and some are regular", () => {
    const childNodes = [{ message: makeMessage("c1", []), children: new Map() }];
    const subagentChildren = new Map([["tu_1", childNodes]]);
    const blocks = [makeToolUse("tu_1", "Task"), makeToolUse("tu_2", "Bash")] as never;
    expect(hasVisibleToolContent(blocks, subagentChildren)).toBe(true);
  });

  it("returns true when message has text plus subagent tool_result (final message on reload)", () => {
    const childNodes = [{ message: makeMessage("c1", []), children: new Map() }];
    const subagentChildren = new Map([["tu_1", childNodes]]);
    const blocks = [makeToolResult("tu_1", "Task"), makeTextBlock("Here are the results...")] as never;
    expect(hasVisibleToolContent(blocks, subagentChildren)).toBe(true);
  });

  it("returns false for empty content", () => {
    expect(hasVisibleToolContent([])).toBe(false);
  });
});
