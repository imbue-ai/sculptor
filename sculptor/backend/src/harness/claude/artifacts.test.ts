import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  readTaskListArtifact,
  shouldRefreshTaskList,
  TranscriptCollector,
} from "~/harness/claude/artifacts";

describe("TranscriptCollector", () => {
  let dir: string;
  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-transcript-"));
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("records stdin/stdout entries and a turn boundary", () => {
    const file = path.join(dir, "transcript.jsonl");
    let clock = 1000;
    const collector = new TranscriptCollector(file, () => clock);
    collector.recordStdin(
      JSON.stringify({
        type: "control_request",
        request: { subtype: "initialize" },
      }),
    );
    collector.recordStdout(
      JSON.stringify({ type: "system", subtype: "task_started" }),
    );
    clock = 3000;
    collector.finalizeTurn("completed");
    collector.close();

    const lines = readFileSync(file, "utf8")
      .trim()
      .split("\n")
      .map((l) => JSON.parse(l));
    expect(lines[0]).toMatchObject({
      direction: "IN",
      msg_type: "control_request",
      subtype: "initialize",
    });
    expect(lines[1]).toMatchObject({
      direction: "OUT",
      msg_type: "system",
      subtype: "task_started",
    });
    expect(lines[2]).toMatchObject({
      turn_boundary: true,
      status: "completed",
      summary: {
        total_count: 2,
        stdin_count: 1,
        stdout_count: 1,
        subagent_count: 1,
        duration_seconds: 2,
      },
    });
  });
});

describe("task-list artifact", () => {
  let dir: string;
  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-tasks-"));
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("reads and id-sorts per-task JSON files, skipping malformed ones", () => {
    writeFileSync(
      path.join(dir, "2.json"),
      JSON.stringify({ id: "2", subject: "second" }),
    );
    writeFileSync(
      path.join(dir, "1.json"),
      JSON.stringify({ id: "1", subject: "first" }),
    );
    writeFileSync(path.join(dir, "bad.json"), "{not json");
    writeFileSync(path.join(dir, "ignore.txt"), "x");
    const artifact = readTaskListArtifact(dir);
    expect(artifact.tasks.map((t) => t.subject)).toEqual(["first", "second"]);
  });

  it("returns an empty artifact for a missing directory", () => {
    expect(readTaskListArtifact(path.join(dir, "nope")).tasks).toEqual([]);
  });

  it("refreshes the task list only for the task tools", () => {
    expect(shouldRefreshTaskList("TaskCreate")).toBe(true);
    expect(shouldRefreshTaskList("TaskUpdate")).toBe(true);
    expect(shouldRefreshTaskList("Bash")).toBe(false);
  });
});
