import { describe, expect, it } from "vitest";

import type { ChatMessage } from "~/projection/chat_types";
import {
  emptyStreamingUpdate,
  type StreamingUpdate,
  type TaskUpdate,
} from "~/projection/streaming_update_types";
import { streamingUpdateToWire } from "~/projection/to_wire";

function messageWithTools(): ChatMessage {
  return {
    role: "ASSISTANT",
    id: "agm_1",
    parent_tool_use_id: "toolu_parent",
    approximate_creation_time: "2026-01-01T00:00:00Z",
    turn_metrics: {
      duration_seconds: 1.5,
      input_tokens: 10,
      output_tokens: 20,
      reasoning_tokens: null,
      changed_files: ["a.ts"],
      context_total_tokens: 100,
      auto_compact_threshold: null,
    },
    stopped: false,
    sent_via: null,
    content: [
      {
        object_type: "ToolUseBlock",
        type: "tool_use",
        id: "toolu_1",
        name: "Edit",
        // Opaque tool args — snake keys here are DATA and must survive verbatim.
        input: { file_path: "/tmp/x", old_string: "a", new_string: "b" },
        interactive_role: null,
      },
      {
        object_type: "ToolResultBlock",
        type: "tool_result",
        tool_use_id: "toolu_1",
        tool_name: "Edit",
        invocation_string: "Edit(/tmp/x)",
        content: { content_type: "diff", diff: "@@", file_path: "/tmp/x" },
        is_error: false,
        duration_seconds: 0.2,
        interactive_role: null,
        description: null,
      },
    ],
  };
}

function taskUpdateFixture(): TaskUpdate {
  return {
    task_id: "tsk_01",
    chat_messages: [messageWithTools()],
    updated_artifacts: [],
    in_progress_chat_message: null,
    queued_chat_messages: [],
    in_progress_user_message_id: null,
    streaming_start_index: 0,
    is_streaming_active: false,
    in_progress_message_was_streamed: false,
    streamed_assistant_message_ids: [],
    streamed_segment_first_response_id: null,
    pending_user_question: null,
    submitted_question_answers: {},
    is_in_plan_mode: false,
    pending_turn_metrics: null,
    pending_background_task_ids: [],
  };
}

function fixtureUpdate(): StreamingUpdate {
  const update = emptyStreamingUpdate();
  update.task_update_by_task_id["tsk_01kvw1abc"] = taskUpdateFixture();
  update.user_update.projects = [
    {
      object_id: "repo_1",
      name: "demo",
      user_git_repo_url: "file:///tmp/demo",
      is_path_accessible: true,
      is_deleted: false,
      default_system_prompt: null,
      workspace_setup_command: null,
      naming_pattern: null,
    },
  ];
  // SculptorSettings is opaque and NOT a to_camel model.
  update.user_update.settings = {
    BIND_HOST: "127.0.0.1",
    TESTING: { INTEGRATION_ENABLED: true },
  };
  return update;
}

describe("streamingUpdateToWire", () => {
  it("camelizes envelope + model field names", () => {
    const wire = streamingUpdateToWire(fixtureUpdate());
    expect(Object.keys(wire)).toContain("taskUpdateByTaskId");
    expect(Object.keys(wire)).toContain("userUpdate");
    expect(Object.keys(wire)).not.toContain("task_update_by_task_id");
    const project = (
      wire.userUpdate as {
        projects: { objectId: string; userGitRepoUrl: string }[];
      }
    ).projects[0]!;
    expect(project.objectId).toBe("repo_1");
    expect(project.userGitRepoUrl).toBe("file:///tmp/demo");
  });

  it("preserves entity-id map keys verbatim", () => {
    const wire = streamingUpdateToWire(fixtureUpdate());
    expect(Object.keys(wire.taskUpdateByTaskId as object)).toEqual([
      "tsk_01kvw1abc",
    ]);
  });

  it("camelizes ChatMessage + block fields but keeps opaque tool payloads", () => {
    const wire = streamingUpdateToWire(fixtureUpdate());
    const task = (
      wire.taskUpdateByTaskId as Record<
        string,
        { chatMessages: Record<string, unknown>[] }
      >
    )["tsk_01kvw1abc"]!;
    const message = task.chatMessages[0]!;
    expect(message.parentToolUseId).toBe("toolu_parent");
    expect(message.sentVia).toBeNull();
    expect(
      (message.turnMetrics as { durationSeconds: number }).durationSeconds,
    ).toBe(1.5);

    const blocks = message.content as Record<string, unknown>[];
    const useBlock = blocks[0]!;
    const resultBlock = blocks[1]!;
    expect(useBlock.objectType).toBe("ToolUseBlock");
    expect(useBlock.interactiveRole).toBeNull();
    // Opaque tool args keep their snake keys (data, not model fields).
    expect(useBlock.input).toEqual({
      file_path: "/tmp/x",
      old_string: "a",
      new_string: "b",
    });

    expect(resultBlock.objectType).toBe("ToolResultBlock");
    expect(resultBlock.toolUseId).toBe("toolu_1");
    expect(
      (resultBlock.content as { contentType: string; filePath: string })
        .contentType,
    ).toBe("diff");
    expect((resultBlock.content as { filePath: string }).filePath).toBe(
      "/tmp/x",
    );
  });

  it("passes SculptorSettings through verbatim (UPPERCASE keys preserved)", () => {
    const wire = streamingUpdateToWire(fixtureUpdate());
    const settings = (wire.userUpdate as { settings: Record<string, unknown> })
      .settings;
    expect(settings.BIND_HOST).toBe("127.0.0.1");
    expect(settings.TESTING).toEqual({ INTEGRATION_ENABLED: true });
  });
});
