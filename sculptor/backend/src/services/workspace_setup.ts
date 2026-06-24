import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";

import {
  spawnBackgroundProcess,
  type BackgroundProcess,
} from "~/environment/process";
import { eventBus } from "~/events";

// The workspace setup-command runner: the TS port of
// services/workspace_service/setup_command_runner.py. After a workspace is
// created, its project's setup command (default `git fetch ...`) runs in the
// working tree; this module owns the status state machine, streams the command
// output to a capped log file, and emits the events the projection turns into
// `workspace_setup_status_by_workspace_id` / `workspace_setup_output_by_workspace_id`.

export const DEFAULT_WORKSPACE_SETUP_COMMAND =
  "git fetch origin 2>/dev/null || true";

export type SetupStatus =
  | "not_configured"
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "legacy";

// Tri-state: null -> default command; "" -> run nothing; other -> custom.
export function resolveWorkspaceSetupCommand(
  stored: string | null,
): string | null {
  if (stored === null) {
    return DEFAULT_WORKSPACE_SETUP_COMMAND;
  }
  if (stored === "") {
    return null;
  }
  return stored;
}

export interface SetupSnapshot {
  status: SetupStatus;
  runId: string | null;
  exitCode: number | null;
  startedAt: number | null;
  finishedAt: number | null;
  logTruncated: boolean;
}

// The wire WorkspaceSetupStatus carried on the stream map (camelCase).
function snapshotToWireStatus(
  workspaceId: string,
  snapshot: SetupSnapshot,
): Record<string, unknown> {
  return {
    workspaceId,
    status: snapshot.status,
    runId: snapshot.runId,
    exitCode: snapshot.exitCode,
    startedAt: snapshot.startedAt,
    finishedAt: snapshot.finishedAt,
    logTruncated: snapshot.logTruncated,
  };
}

const HEAD_BYTES = 512 * 1024;
const TAIL_BYTES = 512 * 1024;
const TRUNCATION_MARKER = "\n... [output truncated] ...\n";
const LOG_FILE_NAME = "setup_log.txt";

// Captures setup-command output into a bounded head + tail buffer, mirroring
// _ChunkHandler / RunnerSlot. The middle is dropped once the head fills and the
// tail overflows; logTruncated records that loss.
class OutputBuffer {
  private head = Buffer.alloc(0);
  private readonly tail: Buffer[] = [];
  private tailSize = 0;
  logTruncated = false;

  append(chunk: Buffer): void {
    if (this.head.length < HEAD_BYTES) {
      const room = HEAD_BYTES - this.head.length;
      this.head = Buffer.concat([this.head, chunk.subarray(0, room)]);
      const overflow = chunk.subarray(room);
      if (overflow.length > 0) {
        this.pushTail(overflow);
      }
      return;
    }
    this.pushTail(chunk);
  }

  private pushTail(chunk: Buffer): void {
    this.tail.push(chunk);
    this.tailSize += chunk.length;
    while (this.tailSize > TAIL_BYTES && this.tail.length > 1) {
      const dropped = this.tail.shift()!;
      this.tailSize -= dropped.length;
      this.logTruncated = true;
    }
  }

  render(): Buffer {
    if (!this.logTruncated && this.tail.length === 0) {
      return this.head;
    }
    return Buffer.concat([
      this.head,
      Buffer.from(TRUNCATION_MARKER),
      ...this.tail,
    ]);
  }
}

interface RunSlot {
  runId: string;
  status: SetupStatus;
  exitCode: number | null;
  startedAt: number;
  finishedAt: number | null;
  process: BackgroundProcess;
  buffer: OutputBuffer;
  seq: number;
  cancelled: boolean;
}

export interface SetupRunnerOptions {
  // Persists the snapshot to the workspace row (so a reconnect/snapshot reflects
  // it). Injected so the runner does not depend on the repository layer directly.
  persist: (
    workspaceId: string,
    snapshot: SetupSnapshot,
    command: string | null,
  ) => void;
  // A monotonically-unique run id (uuid). Injected for determinism in tests.
  newRunId: () => string;
  // The wall clock (seconds). Injected so tests can avoid the Date ban.
  now: () => number;
}

export class WorkspaceSetupRunner {
  private readonly slots = new Map<string, RunSlot>();

  constructor(private readonly options: SetupRunnerOptions) {}

  snapshotOf(workspaceId: string): SetupSnapshot | undefined {
    const slot = this.slots.get(workspaceId);
    if (slot === undefined) {
      return undefined;
    }
    return {
      status: slot.status,
      runId: slot.runId,
      exitCode: slot.exitCode,
      startedAt: slot.startedAt,
      finishedAt: slot.finishedAt,
      logTruncated: slot.buffer.logTruncated,
    };
  }

  isRunning(workspaceId: string): boolean {
    return this.slots.get(workspaceId)?.status === "running";
  }

  // Start (or restart) the setup command for a workspace. Idempotent while a run
  // is already in flight (returns the in-flight snapshot).
  start(
    workspaceId: string,
    workingDir: string,
    command: string,
    stateDir: string,
  ): SetupSnapshot {
    const existing = this.slots.get(workspaceId);
    if (existing !== undefined && existing.status === "running") {
      return this.snapshotOf(workspaceId)!;
    }
    const runId = this.options.newRunId();
    const proc = spawnBackgroundProcess(["sh", "-c", command], {
      cwd: workingDir,
    });
    const slot: RunSlot = {
      runId,
      status: "running",
      exitCode: null,
      startedAt: this.options.now(),
      finishedAt: null,
      process: proc,
      buffer: new OutputBuffer(),
      seq: 0,
      cancelled: false,
    };
    this.slots.set(workspaceId, slot);
    this.emitStatus(workspaceId, command);

    const onChunk = (chunk: Buffer): void => {
      slot.buffer.append(chunk);
      slot.seq += 1;
      eventBus.publish({
        kind: "workspace_setup_output",
        workspaceId,
        chunk: {
          workspaceId,
          runId,
          seq: slot.seq,
          data: chunk.toString("base64"),
        },
      });
    };
    proc.child.stdout?.on("data", onChunk);
    proc.child.stderr?.on("data", onChunk);
    proc.child.on("close", (code) => {
      slot.finishedAt = this.options.now();
      slot.exitCode = slot.cancelled ? null : code;
      slot.status = !slot.cancelled && code === 0 ? "succeeded" : "failed";
      this.writeLog(stateDir, slot);
      this.emitStatus(workspaceId, command);
    });
    proc.child.on("error", () => {
      slot.finishedAt = this.options.now();
      slot.status = "failed";
      this.emitStatus(workspaceId, command);
    });
    return this.snapshotOf(workspaceId)!;
  }

  // Cancel a running setup; returns the failed snapshot, or null when nothing
  // was running.
  cancel(workspaceId: string): SetupSnapshot | null {
    const slot = this.slots.get(workspaceId);
    if (slot === undefined || slot.status !== "running") {
      return null;
    }
    slot.cancelled = true;
    slot.process.child.kill("SIGKILL");
    return this.snapshotOf(workspaceId)!;
  }

  private writeLog(stateDir: string, slot: RunSlot): void {
    try {
      mkdirSync(stateDir, { recursive: true });
      const target = path.join(stateDir, LOG_FILE_NAME);
      const tmp = `${target}.tmp`;
      writeFileSync(tmp, slot.buffer.render());
      renameSync(tmp, target);
    } catch {
      // A failed log write must not crash the run; the status still transitions.
    }
  }

  private emitStatus(workspaceId: string, command: string): void {
    const snapshot = this.snapshotOf(workspaceId)!;
    this.options.persist(workspaceId, snapshot, command);
    eventBus.publish({
      kind: "workspace_setup_status",
      workspaceId,
      status: snapshotToWireStatus(workspaceId, snapshot),
    });
  }
}
