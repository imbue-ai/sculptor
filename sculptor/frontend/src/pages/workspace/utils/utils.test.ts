import { describe, expect, it } from "vitest";

import { getToolDisplayName, getToolDisplayNamePresent, parseBackgroundTaskType } from "./utils.ts";

describe("parseBackgroundTaskType", () => {
  it("returns 'bash' for local_bash content", () => {
    expect(parseBackgroundTaskType("<task_type>local_bash</task_type><status>completed</status>")).toBe("bash");
  });

  it("returns 'agent' for local_agent content", () => {
    expect(parseBackgroundTaskType("<task_type>local_agent</task_type><status>completed</status>")).toBe("agent");
  });

  it("returns 'unknown' when content is undefined", () => {
    expect(parseBackgroundTaskType(undefined)).toBe("unknown");
  });

  it("returns 'unknown' when content has no task_type", () => {
    expect(parseBackgroundTaskType("<status>completed</status>")).toBe("unknown");
  });
});

describe("getToolDisplayName for background task tools", () => {
  describe("TaskOutput", () => {
    it("returns 'Read command output' for bash tasks", () => {
      expect(getToolDisplayName("TaskOutput", "<task_type>local_bash</task_type>")).toBe("Read command output");
    });

    it("returns 'Read subagent output' for agent tasks", () => {
      expect(getToolDisplayName("TaskOutput", "<task_type>local_agent</task_type>")).toBe("Read subagent output");
    });

    it("returns 'Read task output' when task type is unknown", () => {
      expect(getToolDisplayName("TaskOutput")).toBe("Read task output");
    });
  });

  describe("TaskStop", () => {
    it("returns 'Stopped command' for bash tasks", () => {
      expect(getToolDisplayName("TaskStop", "<task_type>local_bash</task_type>")).toBe("Stopped command");
    });

    it("returns 'Stopped subagent' for agent tasks", () => {
      expect(getToolDisplayName("TaskStop", "<task_type>local_agent</task_type>")).toBe("Stopped subagent");
    });

    it("returns 'Stopped task' when task type is unknown", () => {
      expect(getToolDisplayName("TaskStop")).toBe("Stopped task");
    });
  });
});

describe("getToolDisplayNamePresent for background task tools", () => {
  it("returns generic present-tense since task type is unknown before result", () => {
    expect(getToolDisplayNamePresent("TaskOutput")).toBe("Reading task output...");
    expect(getToolDisplayNamePresent("TaskStop")).toBe("Stopping task...");
  });
});
