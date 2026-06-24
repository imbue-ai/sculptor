// Tests for the derived per-agent view (Task 4.3).
//
// Every case was captured by running the REAL Python derived.py
// (`CodingAgentTaskView`) over inputs built the same way the three Python
// derived-test suites build them — web/derived_task_status_test.py,
// web/derived_activity_test.py, web/derived_task_list_test.py — then dumping the
// view fields to JSON (see the task's generator script). The TS
// `computeAgentView` must reproduce those values. The cases pin the status
// branch ORDER (outcome -> terminal signal -> no-environment -> blocked-on-input
// -> request-error), the terminal-agent signal scoping, the activity
// descriptions, and the on-disk task-list artifact extraction.
//
// The task-list artifact URLs embed an absolute path with a `{TMP}` placeholder;
// the test materializes the captured artifact files into a per-run temp dir and
// substitutes the placeholder before computing the view.

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import type { AgentRow } from "~/db/schema/agent";
import type { RunState } from "~/db/schema/enums";
import { computeAgentView } from "~/projection/derived";
import type { RawMessage } from "~/projection/message_log";
import {
  scanTerminalSignalState,
  type TerminalStatusSignal,
} from "~/projection/status";

interface ExpectedView {
  status: string;
  current_activity: string | null;
  last_activity: string | null;
  title: string | null;
  task_completed: number;
  task_total: number;
  current_task_subject: string | null;
  goal: string;
  waiting_detail: string | null;
}

interface Case {
  name: string;
  run_state: string;
  agent_config_object_type: string;
  messages: RawMessage[];
  expected: ExpectedView;
}

interface Fixtures {
  cases: Case[];
  artifact_files: Record<string, string>;
}

const fixturesPath = join(
  dirname(fileURLToPath(import.meta.url)),
  "__fixtures__",
  "derived",
  "derived_views.json",
);

const fixtures = JSON.parse(readFileSync(fixturesPath, "utf8")) as Fixtures;

let tmpDir: string;

beforeAll(() => {
  tmpDir = mkdtempSync(join(tmpdir(), "derived-views-"));
  for (const [basename, contents] of Object.entries(fixtures.artifact_files)) {
    writeFileSync(join(tmpDir, basename), contents);
  }
});

afterAll(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

// Rewrite the `{TMP}` placeholder in artifact URLs to the per-run temp dir.
function resolveMessages(messages: RawMessage[]): RawMessage[] {
  return messages.map((message) => {
    const artifact = message["artifact"] as Record<string, unknown> | undefined;
    if (artifact !== undefined && typeof artifact["url"] === "string") {
      return {
        ...message,
        artifact: { ...artifact, url: (artifact["url"] as string).replace("{TMP}", tmpDir) },
      };
    }
    return message;
  });
}

function makeAgentRow(testCase: Case): AgentRow {
  return {
    objectId: "agent_test",
    createdAt: "2026-06-23T00:00:00Z",
    projectId: "proj_test",
    workspaceId: "ws_test",
    agentConfig: { object_type: testCase.agent_config_object_type },
    startingGitHash: "abc123",
    systemPrompt: null,
    defaultModel: null,
    runState: testCase.run_state as RunState,
    error: null,
    title: null,
    lastProcessedMessageId: null,
    claudeSessionId: null,
    piSessionId: null,
    terminalSessionId: null,
    terminalShellPid: null,
    availableModels: [],
    currentModel: null,
    isDeleted: false,
    isDeleting: false,
    lastReadAt: null,
  };
}

describe("computeAgentView (parity with Python derived.py)", () => {
  it("loads the captured fixture cases", () => {
    expect(fixtures.cases.length).toBeGreaterThanOrEqual(30);
  });

  for (const testCase of fixtures.cases) {
    it(`reproduces the Python view: ${testCase.name}`, () => {
      const view = computeAgentView(makeAgentRow(testCase), resolveMessages(testCase.messages));
      const expected = testCase.expected;
      expect(view.status).toBe(expected.status);
      expect(view.current_activity).toBe(expected.current_activity);
      expect(view.last_activity).toBe(expected.last_activity);
      expect(view.title).toBe(expected.title);
      expect(view.goal).toBe(expected.goal);
      expect(view.task_completed).toBe(expected.task_completed);
      expect(view.task_total).toBe(expected.task_total);
      expect(view.current_task_subject).toBe(expected.current_task_subject);
      expect(view.waiting_detail).toBe(expected.waiting_detail);
    });
  }
});

// Direct unit coverage of the terminal-signal run-scoping subtleties
// (scan_terminal_signal_state): EnvironmentReleased staleness, anchor reset.
describe("scanTerminalSignalState", () => {
  function envAcquired(): RawMessage {
    return { object_type: "EnvironmentAcquiredRunnerMessage" };
  }
  function envReleased(): RawMessage {
    return { object_type: "EnvironmentReleasedRunnerMessage" };
  }
  function signal(value: TerminalStatusSignal): RawMessage {
    return { object_type: "TerminalAgentSignalRunnerMessage", signal: value };
  }

  it("reports not-started with no anchor", () => {
    expect(scanTerminalSignalState([])).toEqual({ runStarted: false, latestSignal: null });
    expect(scanTerminalSignalState([signal("BUSY")])).toEqual({
      runStarted: false,
      latestSignal: null,
    });
  });

  it("returns the latest signal since the most recent run start", () => {
    expect(scanTerminalSignalState([envAcquired(), signal("BUSY"), signal("WAITING")])).toEqual({
      runStarted: true,
      latestSignal: "WAITING",
    });
  });

  it("treats signals before an EnvironmentReleased as stale", () => {
    expect(
      scanTerminalSignalState([envAcquired(), signal("WAITING"), envReleased()]),
    ).toEqual({ runStarted: false, latestSignal: null });
  });

  it("resets at each run-start anchor", () => {
    // A signal before the latest anchor does not survive it.
    expect(scanTerminalSignalState([signal("WAITING"), envAcquired()])).toEqual({
      runStarted: true,
      latestSignal: null,
    });
  });
});
