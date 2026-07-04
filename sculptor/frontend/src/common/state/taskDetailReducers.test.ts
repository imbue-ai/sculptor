import { describe, expect, it } from "vitest";

import type { TaskUpdate, WorkflowTaskState } from "../../api";
import { chatMessagesReducer } from "./taskDetailReducers";

const makeWorkflowState = (status: string): WorkflowTaskState => ({
  objectType: "WorkflowTaskState",
  taskId: "task-wf-1",
  toolUseId: "toolu-wf-1",
  workflowName: "review",
  status,
  entries: [],
  summary: "",
});

const makeCurrentState = (
  workflowTaskStates: Record<string, WorkflowTaskState>,
): Parameters<typeof chatMessagesReducer>[0] => ({
  completedChatMessages: [],
  inProgressChatMessage: null,
  queuedChatMessages: [],
  workingUserMessageId: null,
  pendingUserQuestion: null,
  submittedQuestionAnswers: {},
  isInPlanMode: false,
  pendingBackgroundTaskIds: [],
  workflowTaskStates,
});

const makeTaskUpdate = (overrides: Partial<TaskUpdate>): TaskUpdate =>
  ({
    taskId: "task-1",
    chatMessages: [],
    updatedArtifacts: [],
    inProgressChatMessage: null,
    queuedChatMessages: [],
    inProgressUserMessageId: null,
    streamingStartIndex: 0,
    ...overrides,
  }) as TaskUpdate;

describe("chatMessagesReducer workflowTaskStates", () => {
  it("replaces the map when the update carries one (full-snapshot semantics)", () => {
    const current = makeCurrentState({ "toolu-wf-1": makeWorkflowState("running") });
    const next = chatMessagesReducer(
      current,
      makeTaskUpdate({ workflowTaskStates: { "toolu-wf-1": makeWorkflowState("completed") } }),
    );
    expect(next.workflowTaskStates["toolu-wf-1"]!.status).toBe("completed");
  });

  it("preserves the current map when the update omits the field", () => {
    const current = makeCurrentState({ "toolu-wf-1": makeWorkflowState("running") });
    const next = chatMessagesReducer(current, makeTaskUpdate({ workflowTaskStates: undefined }));
    expect(next.workflowTaskStates["toolu-wf-1"]!.status).toBe("running");
  });

  it("preserves the current map when the update carries null (suppressed as unchanged)", () => {
    const current = makeCurrentState({ "toolu-wf-1": makeWorkflowState("running") });
    const next = chatMessagesReducer(current, makeTaskUpdate({ workflowTaskStates: null }));
    expect(next.workflowTaskStates["toolu-wf-1"]!.status).toBe("running");
  });

  it("replaces a non-empty map with an empty snapshot", () => {
    const current = makeCurrentState({ "toolu-wf-1": makeWorkflowState("running") });
    const next = chatMessagesReducer(current, makeTaskUpdate({ workflowTaskStates: {} }));
    expect(next.workflowTaskStates).toEqual({});
  });
});
