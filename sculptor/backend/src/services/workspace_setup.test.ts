import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_WORKSPACE_SETUP_COMMAND,
  resolveWorkspaceSetupCommand,
  WorkspaceSetupRunner,
  type SetupSnapshot,
} from "~/services/workspace_setup";

describe("resolveWorkspaceSetupCommand", () => {
  it("applies the tri-state semantics", () => {
    expect(resolveWorkspaceSetupCommand(null)).toBe(
      DEFAULT_WORKSPACE_SETUP_COMMAND,
    );
    expect(resolveWorkspaceSetupCommand("")).toBeNull();
    expect(resolveWorkspaceSetupCommand("make setup")).toBe("make setup");
  });
});

describe("WorkspaceSetupRunner", () => {
  let dir: string;
  let runId = 0;
  let clock = 0;
  let persisted: SetupSnapshot[];

  function makeRunner(): WorkspaceSetupRunner {
    runId = 0;
    clock = 0;
    persisted = [];
    return new WorkspaceSetupRunner({
      persist: (_workspaceId, snapshot) => persisted.push(snapshot),
      newRunId: () => `run-${++runId}`,
      now: () => ++clock,
    });
  }

  async function waitUntilDone(
    runner: WorkspaceSetupRunner,
    workspaceId: string,
  ): Promise<SetupSnapshot> {
    for (let i = 0; i < 200; i++) {
      const snapshot = runner.snapshotOf(workspaceId);
      if (snapshot !== undefined && snapshot.status !== "running") {
        return snapshot;
      }
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    throw new Error("setup did not finish");
  }

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-setup-"));
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("runs a command to success and writes the log", async () => {
    const runner = makeRunner();
    const started = runner.start("ws_1", dir, "echo hello", dir);
    expect(started.status).toBe("running");
    expect(started.runId).toBe("run-1");

    const done = await waitUntilDone(runner, "ws_1");
    expect(done.status).toBe("succeeded");
    expect(done.exitCode).toBe(0);
    expect(persisted.some((s) => s.status === "succeeded")).toBe(true);

    const log = readFileSync(path.join(dir, "setup_log.txt"), "utf8");
    expect(log).toContain("hello");
  });

  it("marks a failing command as failed", async () => {
    const runner = makeRunner();
    runner.start("ws_2", dir, "exit 3", dir);
    const done = await waitUntilDone(runner, "ws_2");
    expect(done.status).toBe("failed");
    expect(done.exitCode).toBe(3);
  });

  it("cancels a running command", async () => {
    const runner = makeRunner();
    runner.start("ws_3", dir, "sleep 30", dir);
    expect(runner.isRunning("ws_3")).toBe(true);
    const cancelled = runner.cancel("ws_3");
    expect(cancelled).not.toBeNull();
    const done = await waitUntilDone(runner, "ws_3");
    expect(done.status).toBe("failed");
    expect(done.exitCode).toBeNull();
    expect(runner.cancel("ws_3")).toBeNull();
  });
});
