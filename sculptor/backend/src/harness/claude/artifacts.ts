// Artifact production for the Claude harness: the per-turn transcript
// (`transcript_collector.py`) and the task-list plan artifact
// (`artifact_creation.py` + `harness.get_tasks_path`). These write under the
// agent's `internal/artifacts/` layout (Task 3.1) so the derived view (Task 4.3)
// reads, and the endpoints (Task 6.7) serve, real artifacts.
//
// The git diff-tracker artifact (`diff_tracker.py`) is workspace-level state the
// diff endpoint (Task 6.5) recomputes from git on demand, so it is not
// reproduced here; `should_send_diff_and_branch_name_artifacts` drives that
// refresh via the harness's `onDiffNeeded` hook instead.

import {
  appendFileSync,
  closeSync,
  openSync,
  readdirSync,
  readFileSync,
} from "node:fs";
import path from "node:path";

// --- Transcript collector -------------------------------------------------

const DURATION_PRECISION = 3;

type TranscriptDirection = "IN" | "OUT";

export class TranscriptCollector {
  private readonly fd: number;
  private readonly now: () => number;
  private sequence = 0;
  private turnIndex = 0;
  private turnEntryCount = 0;
  private turnStdinCount = 0;
  private turnStartTime: number | null = null;
  private turnSubagentCount = 0;
  private closed = false;

  constructor(filePath: string, now: () => number = Date.now) {
    this.fd = openSync(filePath, "a");
    this.now = now;
  }

  recordStdin(line: string): void {
    const { msgType, subtype } = classifyStdin(line);
    this.writeEntry("IN", msgType, subtype);
  }

  recordStdout(line: string): void {
    const { msgType, subtype } = classifyStdout(line);
    this.writeEntry("OUT", msgType, subtype);
  }

  finalizeTurn(
    status: "completed" | "interrupted",
    costUsd: number | null = null,
  ): void {
    if (this.closed) {
      return;
    }
    const duration =
      this.turnStartTime !== null
        ? (this.now() - this.turnStartTime) / 1000
        : 0;
    const boundary = {
      turn_boundary: true,
      turn_index: this.turnIndex,
      status,
      summary: {
        total_count: this.turnEntryCount,
        stdin_count: this.turnStdinCount,
        stdout_count: this.turnEntryCount - this.turnStdinCount,
        duration_seconds: round(duration, DURATION_PRECISION),
        cost_usd: costUsd,
        subagent_count: this.turnSubagentCount,
      },
    };
    appendFileSync(this.fd, JSON.stringify(boundary) + "\n");
    this.turnIndex += 1;
    this.turnEntryCount = 0;
    this.turnStdinCount = 0;
    this.turnStartTime = null;
    this.turnSubagentCount = 0;
  }

  close(): void {
    if (this.closed) {
      return;
    }
    this.closed = true;
    closeSync(this.fd);
  }

  private writeEntry(
    direction: TranscriptDirection,
    msgType: string,
    subtype: string | null,
  ): void {
    if (this.closed) {
      return;
    }
    const now = this.now();
    if (this.turnStartTime === null) {
      this.turnStartTime = now;
    }
    const entry: Record<string, unknown> = {
      sequence: this.sequence,
      direction,
      timestamp: now / 1000,
      msg_type: msgType,
    };
    if (subtype !== null) {
      entry.subtype = subtype;
    }
    appendFileSync(this.fd, JSON.stringify(entry) + "\n");
    this.sequence += 1;
    this.turnEntryCount += 1;
    if (direction === "IN") {
      this.turnStdinCount += 1;
    }
    if (subtype === "task_started") {
      this.turnSubagentCount += 1;
    }
  }
}

function classifyStdin(line: string): {
  msgType: string;
  subtype: string | null;
} {
  let data: unknown;
  try {
    data = JSON.parse(line);
  } catch {
    return { msgType: "non_json", subtype: null };
  }
  if (typeof data !== "object" || data === null) {
    return { msgType: "non_object", subtype: null };
  }
  const d = data as Record<string, unknown>;
  const rawType = typeof d.type === "string" ? d.type : "unknown";
  if (rawType === "control_request") {
    const request = (d.request ?? {}) as Record<string, unknown>;
    return {
      msgType: "control_request",
      subtype: typeof request.subtype === "string" ? request.subtype : null,
    };
  }
  return { msgType: rawType, subtype: null };
}

function classifyStdout(line: string): {
  msgType: string;
  subtype: string | null;
} {
  let data: unknown;
  try {
    data = JSON.parse(line);
  } catch {
    return { msgType: "non_json", subtype: null };
  }
  if (typeof data !== "object" || data === null) {
    return { msgType: "non_object", subtype: null };
  }
  const d = data as Record<string, unknown>;
  const rawType = typeof d.type === "string" ? d.type : "unknown";
  if (rawType === "system" || rawType === "result") {
    return {
      msgType: rawType,
      subtype: typeof d.subtype === "string" ? d.subtype : null,
    };
  }
  return { msgType: rawType, subtype: null };
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

// --- Task-list plan artifact ----------------------------------------------

export interface TaskListArtifact {
  tasks: Record<string, unknown>[];
}

// Build a TaskListArtifact by enumerating `$HOME/.claude/tasks/<sessionId>/*.json`
// (the per-task JSON store the CLI writes). Mirrors `_read_task_list_artifact`.
export function readTaskListArtifact(tasksDir: string): TaskListArtifact {
  let entries: string[];
  try {
    entries = readdirSync(tasksDir);
  } catch {
    return { tasks: [] };
  }
  const tasks: Record<string, unknown>[] = [];
  for (const entry of entries) {
    if (!entry.endsWith(".json")) {
      continue;
    }
    try {
      const data = JSON.parse(
        readFileSync(path.join(tasksDir, entry), "utf8"),
      ) as Record<string, unknown>;
      tasks.push(data);
    } catch {
      // Skip one malformed file rather than blanking the whole list.
      continue;
    }
  }
  tasks.sort((a, b) => taskSortKey(a) - taskSortKey(b));
  return { tasks };
}

function taskSortKey(task: Record<string, unknown>): number {
  const id = Number(task.id);
  return Number.isFinite(id) ? id : Number.MAX_SAFE_INTEGER;
}

// Whether a tool_result for this tool should re-read the per-task JSON store.
export function shouldRefreshTaskList(toolName: string): boolean {
  return toolName === "TaskCreate" || toolName === "TaskUpdate";
}
