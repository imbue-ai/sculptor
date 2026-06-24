import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { mkdir, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { AgentRow } from "~/db/schema";
import {
  ClaudeHarness,
  computeClaudeJsonlDirectory,
  type ClaudeHarnessEnvironment,
} from "~/harness/claude/harness";
import { resolveJsonlDirectory } from "~/harness/claude/paths";
import type { HarnessExitResult } from "~/runner/harness";

describe("ClaudeHarness — identity", () => {
  const harness = new ClaudeHarness({
    resolveBinaryPath: () => "/bin/claude",
    environmentFor: () => ({}) as ClaudeHarnessEnvironment,
    initializationStrategyFor: () => "WORKTREE",
  });

  it("classifies the backchannel tools (built-in + MCP names)", () => {
    expect(harness.isAskUserQuestionTool("AskUserQuestion")).toBe(true);
    expect(
      harness.isAskUserQuestionTool("mcp__sculptor__ask_user_question"),
    ).toBe(true);
    expect(harness.isExitPlanModeTool("mcp__sculptor__exit_plan_mode")).toBe(
      true,
    );
    expect(harness.isAskUserQuestionTool("Bash")).toBe(false);
  });

  it("exposes the Claude model catalog and selection", () => {
    expect(harness.getAvailableModels()).toContain("CLAUDE-4-OPUS");
    expect(
      harness.getSelectedModelId({
        defaultModel: "CLAUDE-4-SONNET",
      } as AgentRow),
    ).toBe("CLAUDE-4-SONNET");
    expect(
      harness.getSelectedModelId({ defaultModel: null } as AgentRow),
    ).toBeNull();
  });

  it("computes the session-JSONL directory by sanitizing the working dir", () => {
    expect(computeClaudeJsonlDirectory("/home/u", "/a/b/code", {})).toBe(
      "/home/u/.claude/projects/-a-b-code",
    );
    expect(
      computeClaudeJsonlDirectory("/home/u", "/a/b/code", {
        CLAUDE_CONFIG_DIR: "/custom",
      }),
    ).toBe("/custom/projects/-a-b-code");
  });
});

// A fake `claude` binary that ignores stdin and emits a scripted stream-json
// turn. If SCULPTOR_FAKE_ARGV_OUT is set it first records the CLI flags it was
// launched with (used to assert the `--resume` wiring).
function writeFakeClaude(dir: string, sessionId: string): string {
  const script = `#!/usr/bin/env node
import { writeFileSync } from "node:fs";
const out = process.env.SCULPTOR_FAKE_ARGV_OUT;
if (out) writeFileSync(out, process.argv.slice(2).join(" "));
const lines = [
  { type: "system", subtype: "init", session_id: ${JSON.stringify(sessionId)} },
  { type: "assistant", message: { id: "asst_1", content: [{ type: "text", text: "hi there" }] } },
  { type: "result", is_error: false, result: "done", usage: { input_tokens: 3, output_tokens: 2 } },
];
process.stdout.write(lines.map((l) => JSON.stringify(l)).join("\\n") + "\\n", () => process.exit(0));
`;
  const file = path.join(dir, "fake-claude.mjs");
  writeFileSync(file, script);
  chmodSync(file, 0o755);
  return file;
}

function makeEnvironment(root: string): ClaudeHarnessEnvironment {
  return {
    getUserHomeDirectory: () => root,
    getWorkingDirectory: () => root,
    getStatePath: (agentId) => path.join(root, "state", agentId),
    getArtifactsPath: (agentId) => path.join(root, "artifacts", agentId),
    writeFile: async (p, content) => {
      await mkdir(path.dirname(p), { recursive: true });
      await import("node:fs/promises").then((fs) => fs.writeFile(p, content));
    },
    readTextFile: (p) => readFile(p, "utf8"),
  };
}

const AGENT = {
  objectId: "tsk_int",
  projectId: "prj_1",
  defaultModel: "FAKE_CLAUDE",
  systemPrompt: null,
} as unknown as AgentRow;

// Generous timeout: these tests spawn a real subprocess, and under the full
// parallel suite many spawns contend, so the default 5s can be exceeded.
const E2E_TIMEOUT_MS = 20_000;

async function waitFor(
  predicate: () => boolean,
  timeoutMs = E2E_TIMEOUT_MS - 2_000,
): Promise<void> {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error("timed out waiting for condition");
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

describe("ClaudeHarness — end-to-end turn against a fake binary", () => {
  let dir: string;
  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-claude-"));
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it(
    "brackets the turn with RequestStarted/RequestSuccess and persists the session id",
    async () => {
      const binary = writeFakeClaude(dir, "sess_int");
      const harness = new ClaudeHarness({
        resolveBinaryPath: () => binary,
        environmentFor: () => makeEnvironment(dir),
        initializationStrategyFor: () => "WORKTREE",
      });
      const messages: Record<string, unknown>[] = [];
      const process = harness.launch({ agent: AGENT, workingDirectory: dir });
      process.onMessage((m) => messages.push(m));
      process.onExit(() => undefined);
      process.sendUserMessage({
        message_id: "agm_user_1",
        text: "hello",
        model_name: "FAKE_CLAUDE",
      });

      await waitFor(() =>
        messages.some((m) => m.object_type === "RequestSuccessAgentMessage"),
      );

      const objectTypes = messages.map((m) => m.object_type);
      expect(objectTypes).toEqual([
        "RequestStartedAgentMessage",
        "ResponseBlockAgentMessage",
        "TurnMetricsAgentMessage",
        "RequestSuccessAgentMessage",
      ]);
      expect(messages[0]).toMatchObject({ request_id: "agm_user_1" });
      expect(messages.at(-1)).toMatchObject({
        request_id: "agm_user_1",
        interrupted: false,
      });

      // The session-id persistence is best-effort within the turn (the next
      // turn reads it), so wait for the file rather than assuming it landed
      // exactly by RequestSuccess.
      const sessionFile = path.join(dir, "state", "tsk_int", "session_id");
      await waitFor(() => existsSync(sessionFile));
      expect(await readFile(sessionFile, "utf8")).toBe("sess_int");
    },
    E2E_TIMEOUT_MS,
  );

  it(
    "fails the agent when the binary is missing",
    async () => {
      const harness = new ClaudeHarness({
        resolveBinaryPath: () => undefined,
        environmentFor: () => makeEnvironment(dir),
        initializationStrategyFor: () => "WORKTREE",
      });
      const messages: Record<string, unknown>[] = [];
      let exit: HarnessExitResult | undefined;
      const process = harness.launch({ agent: AGENT, workingDirectory: dir });
      process.onMessage((m) => messages.push(m));
      process.onExit((r) => (exit = r));
      process.sendUserMessage({ message_id: "agm_user_1", text: "hello" });

      await waitFor(() => exit !== undefined);
      expect(messages.map((m) => m.object_type)).toEqual([
        "RequestStartedAgentMessage",
        "RequestFailureAgentMessage",
      ]);
      expect((exit?.error as { exception: string }).exception).toBe(
        "ClaudeBinaryNotFoundError",
      );
    },
    E2E_TIMEOUT_MS,
  );
});

describe("ClaudeHarness — session resume (Task 5.4)", () => {
  let dir: string;
  let cfg: string;
  let prevCfg: string | undefined;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-claude-"));
    cfg = mkdtempSync(path.join(tmpdir(), "sculptor-claude-cfg-"));
    prevCfg = process.env.CLAUDE_CONFIG_DIR;
    process.env.CLAUDE_CONFIG_DIR = cfg;
  });
  afterEach(() => {
    if (prevCfg === undefined) {
      delete process.env.CLAUDE_CONFIG_DIR;
    } else {
      process.env.CLAUDE_CONFIG_DIR = prevCfg;
    }
    rmSync(dir, { recursive: true, force: true });
    rmSync(cfg, { recursive: true, force: true });
  });

  // Seed a session JSONL where the harness will look for the given working dir.
  function seedValidSession(
    home: string,
    workingDir: string,
    sessionId: string,
  ): void {
    const jsonlDir = resolveJsonlDirectory(home, workingDir);
    mkdirSync(jsonlDir, { recursive: true });
    writeFileSync(
      path.join(jsonlDir, `${sessionId}.jsonl`),
      JSON.stringify({ type: "assistant", sessionId, message: { id: "a" } }),
    );
  }

  async function runResumeTurn(
    env: ClaudeHarnessEnvironment,
    binary: string,
    argvFile: string,
  ): Promise<Record<string, unknown>[]> {
    const harness = new ClaudeHarness({
      resolveBinaryPath: () => binary,
      environmentFor: () => env,
      initializationStrategyFor: () => "WORKTREE",
    });
    const messages: Record<string, unknown>[] = [];
    const agentProcess = harness.launch({
      agent: AGENT,
      workingDirectory: dir,
      env: { SCULPTOR_FAKE_ARGV_OUT: argvFile },
    });
    agentProcess.onMessage((m) => messages.push(m));
    agentProcess.onExit(() => undefined);
    agentProcess.sendUserMessage({
      message_id: "agm_u",
      text: "hi",
      model_name: "FAKE_CLAUDE",
    });
    await waitFor(() =>
      messages.some((m) => m.object_type === "RequestSuccessAgentMessage"),
    );
    return messages;
  }

  it(
    "passes --resume for a valid session",
    async () => {
      const binary = writeFakeClaude(dir, "sess_new");
      const argvFile = path.join(dir, "argv.txt");
      const env = makeEnvironment(dir);
      await env.writeFile(
        path.join(env.getStatePath("tsk_int"), "session_id"),
        "sess_resume",
      );
      seedValidSession(dir, dir, "sess_resume");

      const messages = await runResumeTurn(env, binary, argvFile);
      expect(readFileSync(argvFile, "utf8")).toContain("--resume sess_resume");
      expect(
        messages.some((m) => m.object_type === "WarningAgentMessage"),
      ).toBe(false);
    },
    E2E_TIMEOUT_MS,
  );

  it(
    "rolls back to the validated session when the primary pointer is invalid",
    async () => {
      const binary = writeFakeClaude(dir, "sess_new");
      const argvFile = path.join(dir, "argv.txt");
      const env = makeEnvironment(dir);
      // Primary pointer references a session with no on-disk file (invalid);
      // the validated fallback is a real, resumable session.
      await env.writeFile(
        path.join(env.getStatePath("tsk_int"), "session_id"),
        "sess_missing",
      );
      await env.writeFile(
        path.join(env.getStatePath("tsk_int"), "validated_session_id"),
        "sess_valid_prev",
      );
      seedValidSession(dir, dir, "sess_valid_prev");

      const messages = await runResumeTurn(env, binary, argvFile);
      expect(readFileSync(argvFile, "utf8")).toContain(
        "--resume sess_valid_prev",
      );
      expect(
        messages.some((m) => m.object_type === "WarningAgentMessage"),
      ).toBe(true);
    },
    E2E_TIMEOUT_MS,
  );
});
