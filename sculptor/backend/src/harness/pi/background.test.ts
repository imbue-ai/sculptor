import { describe, expect, it } from "vitest";

import {
  BACKGROUND_NOTIFY_MARKER,
  formatBackgroundCompletion,
  parseBackgroundCompletion,
  parseBackgroundStart,
} from "~/harness/pi/background";

describe("background lifecycle parsing", () => {
  it("parses a launch snapshot", () => {
    const result = {
      details: {
        v: 1,
        task: {
          taskId: "bg1",
          toolCallId: "tc1",
          label: "build",
          command: "npm run build",
          pgid: 222,
          status: "running",
        },
      },
    };
    expect(parseBackgroundStart(result)).toEqual({
      taskId: "bg1",
      toolCallId: "tc1",
      label: "build",
      command: "npm run build",
      pgid: 222,
      status: "running",
    });
  });

  it("parses a completion notify", () => {
    const message = JSON.stringify({
      [BACKGROUND_NOTIFY_MARKER]: {
        v: 1,
        taskId: "bg1",
        toolCallId: "tc1",
        status: "completed",
        exitCode: 0,
        summary: "done",
        durationMs: 5000,
      },
    });
    expect(parseBackgroundCompletion(message)).toEqual({
      taskId: "bg1",
      toolCallId: "tc1",
      status: "completed",
      exitCode: 0,
      summary: "done",
      durationMs: 5000,
    });
  });

  it("rejects foreign / wrong-version notifies", () => {
    expect(parseBackgroundCompletion(JSON.stringify({ other: {} }))).toBeNull();
    expect(
      parseBackgroundCompletion(
        JSON.stringify({ [BACKGROUND_NOTIFY_MARKER]: { v: 9 } }),
      ),
    ).toBeNull();
  });

  it("formats a completion summary", () => {
    expect(
      formatBackgroundCompletion({
        taskId: "b",
        toolCallId: "c",
        status: "completed",
        exitCode: 0,
        summary: "log tail",
        durationMs: null,
      }),
    ).toBe("Background task completed (exit code 0).\n\nlog tail");
    expect(
      formatBackgroundCompletion({
        taskId: "b",
        toolCallId: "c",
        status: "failed",
        exitCode: null,
        summary: "",
        durationMs: null,
      }),
    ).toBe("Background task failed.");
  });
});
