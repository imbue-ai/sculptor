// Crash-recovery message replay (RW-DATA-6). On restart the runner re-supervises
// every non-terminal agent (runner.ts) but the relaunched harness comes up with
// an empty in-memory queue, so any user message that had not finished its turn
// before the shutdown would be stranded: an interrupted in-flight turn never
// reaches a terminal Request* (status stays RUNNING forever) and a queued
// follow-up is never dispatched (it sits in the queued bar). This module derives,
// from the persisted append-only log, exactly which user messages still need to
// run and how to re-deliver each one to the harness.
//
// Two kinds of unprocessed user message, recovered via different paths (matching
// the Python run_agent loop the harness ports):
//
//   - in-flight: a user message whose turn STARTED (a RequestStartedAgentMessage
//     was persisted) but never finished. The model already received the original
//     prompt and may have streamed a partial response, so we must NOT re-send the
//     prompt (that would duplicate the streamed output); we resume the model
//     session with a short "continue" instruction, keyed to the ORIGINAL
//     request_id so the turn's completion finalizes it.
//   - never-started: a user message that was queued behind the in-flight turn and
//     never got a RequestStarted. The model never saw it, so it is re-dispatched
//     verbatim as a fresh turn.

const FINISHED_REQUEST_OBJECT_TYPES: ReadonlySet<string> = new Set<string>([
  "RequestSuccessAgentMessage",
  "RequestFailureAgentMessage",
  "RequestStoppedAgentMessage",
  "RequestSkippedAgentMessage",
]);

const USER_MESSAGE_OBJECT_TYPES: ReadonlySet<string> = new Set<string>([
  "ChatInputUserMessage",
  "UserQuestionAnswerMessage",
]);

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

// Re-deliver the messages this returns, in order, to a freshly relaunched
// harness to recover the agent's in-flight + queued turns after a restart.
export function computeReplayPlan(
  messages: readonly Record<string, unknown>[],
): Record<string, unknown>[] {
  const finishedRequestIds = new Set<string>();
  const startedRequestIds = new Set<string>();
  const removedMessageIds = new Set<string>();
  for (const message of messages) {
    const type = asString(message["object_type"]);
    if (type === undefined) {
      continue;
    }
    if (FINISHED_REQUEST_OBJECT_TYPES.has(type)) {
      const requestId = asString(message["request_id"]);
      if (requestId !== undefined) {
        finishedRequestIds.add(requestId);
      }
    } else if (type === "RequestStartedAgentMessage") {
      const requestId = asString(message["request_id"]);
      if (requestId !== undefined) {
        startedRequestIds.add(requestId);
      }
    } else if (type === "RemoveQueuedMessageAgentMessage") {
      const removedId = asString(message["removed_message_id"]);
      if (removedId !== undefined) {
        removedMessageIds.add(removedId);
      }
    }
  }

  const plan: Record<string, unknown>[] = [];
  // The last model a turn ran under, threaded forward so a recovered follow-up
  // that did not pin its own model still runs under the right one (the live
  // harness keeps this in memory across turns; a restart loses it).
  let lastModelName: string | undefined;
  for (const message of messages) {
    const type = asString(message["object_type"]);
    if (type === undefined || !USER_MESSAGE_OBJECT_TYPES.has(type)) {
      continue;
    }
    const messageId = asString(message["message_id"]);
    if (messageId === undefined) {
      continue;
    }
    const messageModel = asString(message["model_name"]);
    if (messageModel !== undefined && messageModel !== "") {
      lastModelName = messageModel;
    }
    if (finishedRequestIds.has(messageId) || removedMessageIds.has(messageId)) {
      continue;
    }
    if (startedRequestIds.has(messageId)) {
      // In-flight: resume the session, do not replay the prompt.
      const resume: Record<string, unknown> = {
        object_type: type,
        message_id: messageId,
        source: "USER",
        is_resume: true,
      };
      if (lastModelName !== undefined) {
        resume["model_name"] = lastModelName;
      }
      plan.push(resume);
    } else {
      // Never-started: re-dispatch the original message verbatim, filling in the
      // model only if it never carried one.
      if ((messageModel === undefined || messageModel === "") && lastModelName !== undefined) {
        plan.push({ ...message, model_name: lastModelName });
      } else {
        plan.push(message);
      }
    }
  }
  return plan;
}
