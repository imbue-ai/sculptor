// The hello/test harness — a trivial echo harness the integration suite uses
// for non-Claude/non-Pi agent paths (ports `agents/hello_agent`). Each user
// message is bracketed by RequestStarted/RequestSuccess with a single echoed
// assistant ResponseBlock, so the projection renders a turn without a
// real CLI.

import { newAgentMessageId } from "~/ids";
import { makeTextBlock } from "~/harness/claude/stream_parser";
import type {
  Harness,
  HarnessExitResult,
  HarnessProcess,
} from "~/runner/harness";

export class HelloHarness implements Harness {
  readonly name = "hello";

  launch(): HarnessProcess {
    return new HelloHarnessProcess();
  }
}

class HelloHarnessProcess implements HarnessProcess {
  private messageCb: ((message: Record<string, unknown>) => void) | undefined;
  private exitCb: ((result: HarnessExitResult) => void) | undefined;
  private finished = false;

  onMessage(callback: (message: Record<string, unknown>) => void): void {
    this.messageCb = callback;
  }

  onExit(callback: (result: HarnessExitResult) => void): void {
    this.exitCb = callback;
  }

  sendUserMessage(message: Record<string, unknown>): void {
    if (this.finished) {
      return;
    }
    const requestId =
      typeof message.message_id === "string"
        ? message.message_id
        : newAgentMessageId();
    const text = typeof message.text === "string" ? message.text : "";
    const now = new Date().toISOString();
    this.emit({
      object_type: "RequestStartedAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      request_id: requestId,
    });
    this.emit({
      object_type: "ResponseBlockAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      assistant_message_id: newAgentMessageId(),
      content: [makeTextBlock(text)],
      parent_tool_use_id: null,
      approximate_creation_time: now,
    });
    this.emit({
      object_type: "RequestSuccessAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      request_id: requestId,
      interrupted: false,
      approximate_creation_time: now,
    });
  }

  interrupt(): void {
    // No long-running turn to interrupt.
  }

  stop(): void {
    this.finished = true;
  }

  private emit(message: Record<string, unknown>): void {
    this.messageCb?.(message);
  }
}
