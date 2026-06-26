import { describe, expect, it } from "vitest";

import { computeReplayPlan } from "~/runner/replay";

function chatInput(id: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { object_type: "ChatInputUserMessage", message_id: id, source: "USER", text: `text-${id}`, ...extra };
}

function started(requestId: string): Record<string, unknown> {
  return { object_type: "RequestStartedAgentMessage", message_id: `start-${requestId}`, source: "AGENT", request_id: requestId };
}

function success(requestId: string): Record<string, unknown> {
  return { object_type: "RequestSuccessAgentMessage", message_id: `done-${requestId}`, source: "AGENT", request_id: requestId };
}

describe("computeReplayPlan", () => {
  it("returns nothing when there are no messages", () => {
    expect(computeReplayPlan([])).toEqual([]);
  });

  it("does not replay a turn that already finished", () => {
    const plan = computeReplayPlan([chatInput("a"), started("a"), success("a")]);
    expect(plan).toEqual([]);
  });

  it("resumes an in-flight turn without replaying its prompt", () => {
    const plan = computeReplayPlan([chatInput("a", { model_name: "m1" }), started("a")]);
    expect(plan).toEqual([
      { object_type: "ChatInputUserMessage", message_id: "a", source: "USER", is_resume: true, model_name: "m1" },
    ]);
  });

  it("re-dispatches a never-started queued message verbatim", () => {
    const queued = chatInput("b", { model_name: "m1" });
    const plan = computeReplayPlan([queued, started("a"), queued]);
    // The queued message (no RequestStarted of its own) is sent as-is.
    expect(plan).toContainEqual(queued);
  });

  it("recovers an in-flight turn and the follow-up queued behind it, in order", () => {
    const a = chatInput("a", { model_name: "m1" });
    const b = chatInput("b");
    const plan = computeReplayPlan([a, started("a"), b]);
    expect(plan).toEqual([
      { object_type: "ChatInputUserMessage", message_id: "a", source: "USER", is_resume: true, model_name: "m1" },
      { ...b, model_name: "m1" },
    ]);
  });

  it("skips a queued message that was removed before the restart", () => {
    const b = chatInput("b");
    const removal = {
      object_type: "RemoveQueuedMessageAgentMessage",
      message_id: "rm-b",
      source: "AGENT",
      removed_message_id: "b",
    };
    expect(computeReplayPlan([b, removal])).toEqual([]);
  });

  it("threads the last model forward to a follow-up that did not pin one", () => {
    const a = chatInput("a", { model_name: "opus" });
    const b = chatInput("b");
    const plan = computeReplayPlan([a, started("a"), success("a"), b]);
    expect(plan).toEqual([{ ...b, model_name: "opus" }]);
  });
});
