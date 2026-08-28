/**
 * Composable scenario functions for Storybook fixtures.
 *
 * Each function returns a ReadonlyArray<ChatMessage> focused on one feature
 * category from the feature inventory. Scenarios are meant to be used directly
 * as story args — one scenario per story variant.
 */

import type { ChatMessage } from "~/api";

import { blocks, msg, resetCounters } from "./messageBuilders.ts";

/** Simple multi-turn conversation with text-only messages. */
export const basicConversation = (): ReadonlyArray<ChatMessage> => {
  resetCounters();
  return [
    msg.user("Can you help me refactor this function to use async/await instead of callbacks?"),
    msg.assistantText("Sure! I'll read the file first to understand the current implementation."),
    msg.user("Looks good! Can you also add error handling?"),
    msg.assistantText("Of course. I'll wrap the async call in a try/catch block and add proper error types."),
  ];
};

/** Conversation with tool_use and tool_result blocks. */
export const toolExecution = (): ReadonlyArray<ChatMessage> => {
  resetCounters();
  const readTool = blocks.toolUse("Read", { file_path: "/src/utils/fetch.ts" });
  const bashTool = blocks.toolUse("Bash", { command: "npm test" });

  return [
    msg.user("Can you read the fetch utility and run the tests?"),
    msg.assistant([blocks.text("I'll read the file first."), readTool]),
    msg.assistant([
      blocks.toolResult(
        readTool.id,
        "Read",
        "function fetchData(callback) {\n  http.get('/api/data', (res) => {\n    callback(null, res);\n  });\n}",
      ),
    ]),
    msg.assistant([blocks.text("Now I'll run the tests."), bashTool]),
    msg.assistant([blocks.toolResult(bashTool.id, "Bash", "All 42 tests passed.")]),
    msg.assistantText("Everything looks good. The tests all pass."),
  ];
};

/** Messages showing error and warning system blocks. */
export const errorsAndWarnings = (): ReadonlyArray<ChatMessage> => {
  resetCounters();
  return [
    msg.user("Run the tests and fix any failures."),
    msg.assistantText("I'll run the tests now."),
    msg.assistant([blocks.warning("Test suite has 1 failure. Attempting automatic fix.", "test_failure")]),
    msg.assistant([
      blocks.error(
        "Rate limit exceeded. Please wait before retrying.",
        "api.RateLimitError",
        'Traceback (most recent call last):\n  File "agent.py", line 42\n    raise RateLimitError("Rate limit exceeded")',
      ),
    ]),
  ];
};

/** Messages showing context summary, context cleared, and resume. */
export const contextManagement = (): ReadonlyArray<ChatMessage> => {
  resetCounters();
  return [
    msg.user("Help me debug this issue."),
    msg.assistantText("I'll investigate the logs."),
    msg.assistant([
      blocks.contextSummary(
        "Previous conversation covered: user asked to debug a network issue, " +
          "logs showed timeout errors on the /api/data endpoint, suggested increasing " +
          "the request timeout from 5s to 30s.",
      ),
    ]),
    msg.user("Start fresh on a different task."),
    msg.assistant([blocks.contextCleared(), blocks.text("Context cleared. Ready for a new task.")]),
  ];
};

/** Messages with parentToolUseId showing subagent nesting. */
export const subagentNesting = (): ReadonlyArray<ChatMessage> => {
  resetCounters();
  const taskTool = blocks.toolUse("Agent", {
    prompt:
      "Analyze the database layer in sculptor/sculptor/database/, Read the models, migrations, and query patterns to understand the schema design and identify any potential performance issues with the current indexing strategy",
    subagent_type: "Explore",
  });

  return [
    msg.user("Fix the failing tests."),
    msg.assistant([blocks.text("I'll spawn a subagent to explore the test setup."), taskTool]),
    // Subagent messages
    msg.assistant(
      [
        blocks.text("Exploring the test file to understand the mock setup..."),
        blocks.toolUse("Read", { file_path: "/src/utils/fetch.test.ts" }),
      ],
      { parentToolUseId: taskTool.id },
    ),
    msg.assistant([blocks.text("Found the issue — missing global fetch mock in the test setup file.")], {
      parentToolUseId: taskTool.id,
    }),
    // Back to main agent
    msg.assistant([
      blocks.toolResult(taskTool.id, "Agent", "Subagent found: missing global fetch mock in test setup."),
    ]),
    msg.assistantText("The subagent identified the problem. I'll add the fetch mock now."),
  ];
};

/** Every block type in a single conversation. Useful for view-level stories. */
export const kitchenSink = (): ReadonlyArray<ChatMessage> => {
  resetCounters();
  const readTool = blocks.toolUse("Read", { file_path: "/src/utils/fetch.ts" });
  const bashTool = blocks.toolUse("Bash", { command: "npm test" });
  const taskTool = blocks.toolUse("Task", { description: "Explore test setup" });

  return [
    msg.user("Run the test suite and fix any failures."),
    msg.assistant([blocks.text("I'll run the tests now."), bashTool]),
    msg.assistant([
      blocks.toolResult(
        bashTool.id,
        "Bash",
        "FAIL src/utils/fetch.test.ts\n  ● fetchData › should handle network errors\n    TypeError: fetch is not defined",
        true,
      ),
    ]),
    msg.assistant([blocks.warning("Test suite has 1 failure. Attempting automatic fix.", "test_failure")]),
    msg.assistant([blocks.text("I'll spawn a subagent to investigate."), taskTool]),
    msg.assistant([blocks.text("Exploring the test file..."), readTool], { parentToolUseId: taskTool.id }),
    msg.assistant([
      blocks.error(
        "Rate limit exceeded. Please wait before retrying.",
        "api.RateLimitError",
        'Traceback (most recent call last):\n  File "agent.py", line 42\n    raise RateLimitError("Rate limit exceeded")',
      ),
    ]),
    msg.assistant([
      blocks.resumeResponse(),
      blocks.text("Resuming after rate limit cleared. I've fixed the test by adding a global fetch mock."),
    ]),
    msg.assistant([
      blocks.contextSummary(
        "Previous conversation: user asked to run tests, 1 failure in fetch.test.ts, " +
          "rate limit interrupted the fix, resumed and applied the fix.",
      ),
    ]),
    msg.user("Start fresh on a different task."),
    msg.assistant([blocks.contextCleared(), blocks.text("Context cleared. Ready for a new task.")]),
    msg.user("Show me the architecture diagram."),
    msg.assistant([blocks.text("Here's the diagram:"), blocks.file("/Users/developer/project/docs/architecture.png")]),
  ];
};
