import {
  chmodSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { AgentRow } from "~/db/schema";
import { PiHarness, type PiHarnessEnvironment } from "~/harness/pi/harness";
import type { HarnessExitResult } from "~/runner/harness";

describe("PiHarness — identity", () => {
  const harness = new PiHarness({
    resolveBinaryPath: () => "/bin/pi",
    environmentFor: () => ({}) as PiHarnessEnvironment,
    initializationStrategyFor: () => "WORKTREE",
  });

  it("classifies pi's backchannel tools", () => {
    expect(harness.isAskUserQuestionTool("ask_user_question")).toBe(true);
    expect(harness.isExitPlanModeTool("exit_plan_mode")).toBe(true);
    expect(harness.isAskUserQuestionTool("bash")).toBe(false);
  });

  it("reads the model catalog + selection off the agent row", () => {
    const agent = {
      availableModels: [
        { provider: "anthropic", model_id: "m1", display_name: "M1" },
      ],
      currentModel: {
        provider: "anthropic",
        model_id: "m1",
        display_name: "M1",
      },
    } as unknown as AgentRow;
    expect(harness.getAvailableModels(agent)).toHaveLength(1);
    expect(harness.getSelectedModelId(agent)).toBe("m1");
    expect(
      harness.getSelectedModelId({ currentModel: null } as AgentRow),
    ).toBeNull();
  });
});

// A fake `pi --mode rpc` binary: answers get_available_models / get_state, and
// scripts one assistant turn per prompt. Stays alive (readline keeps the loop).
function writeFakePi(dir: string): string {
  const script = `#!/usr/bin/env node
import { createInterface } from "node:readline";
const MODEL = { id: "fake-pi-opus-4-8", name: "FakePi Opus", provider: "anthropic" };
const SESSION = process.argv[process.argv.indexOf("--session-id") + 1] || "s";
const send = (o) => process.stdout.write(JSON.stringify(o) + "\\n");
const rl = createInterface({ input: process.stdin });
rl.on("line", (line) => {
  let cmd;
  try { cmd = JSON.parse(line); } catch { return; }
  if (cmd.type === "get_available_models") send({ type: "response", command: "get_available_models", success: true, id: cmd.id, data: { models: [MODEL] } });
  else if (cmd.type === "get_state") send({ type: "response", command: "get_state", success: true, id: cmd.id, data: { sessionId: SESSION, messageCount: 0, model: MODEL } });
  else if (cmd.type === "prompt") {
    send({ type: "response", command: "prompt", success: true, id: cmd.id });
    send({ type: "agent_start" });
    send({ type: "message_update", message: { role: "assistant", content: [] }, assistantMessageEvent: { type: "text_delta", delta: "hi there" } });
    send({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "hi there" }], stopReason: "stop" } });
    send({ type: "agent_end", messages: [], willRetry: false });
  } else if (cmd.type === "abort") send({ type: "response", command: "abort", success: true });
});
`;
  const file = path.join(dir, "fake-pi.mjs");
  writeFileSync(file, script);
  chmodSync(file, 0o755);
  return file;
}

function makeEnvironment(root: string): PiHarnessEnvironment {
  return {
    getWorkingDirectory: () => root,
    getStatePath: (agentId) => path.join(root, "state", agentId),
    writeFile: async (p, content) => {
      await mkdir(path.dirname(p), { recursive: true });
      await writeFile(p, content);
    },
    readTextFile: (p) => readFile(p, "utf8"),
  };
}

const AGENT = {
  objectId: "tsk_pi",
  projectId: "prj_1",
  systemPrompt: null,
  availableModels: [],
  currentModel: null,
} as unknown as AgentRow;

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

describe("PiHarness — end-to-end turn against a fake pi binary", () => {
  let dir: string;
  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-pi-"));
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it(
    "fetches models, runs a turn, and persists the session id",
    async () => {
      const binary = writeFakePi(dir);
      const harness = new PiHarness({
        resolveBinaryPath: () => binary,
        environmentFor: () => makeEnvironment(dir),
        initializationStrategyFor: () => "WORKTREE",
      });
      const messages: Record<string, unknown>[] = [];
      const agentProcess = harness.launch({
        agent: AGENT,
        workingDirectory: dir,
      });
      agentProcess.onMessage((m) => messages.push(m));
      agentProcess.onExit(() => undefined);
      agentProcess.sendUserMessage({ message_id: "agm_u", text: "hello" });

      await waitFor(() =>
        messages.some((m) => m.object_type === "RequestSuccessAgentMessage"),
      );
      agentProcess.stop();

      const objectTypes = messages.map((m) => m.object_type);
      expect(objectTypes).toContain("ModelsAvailableAgentMessage");
      expect(objectTypes).toContain("RequestStartedAgentMessage");
      expect(objectTypes).toContain("ResponseBlockAgentMessage");
      expect(messages.at(-1)).toMatchObject({
        object_type: "RequestSuccessAgentMessage",
        request_id: "agm_u",
        interrupted: false,
      });

      const models = messages.find(
        (m) => m.object_type === "ModelsAvailableAgentMessage",
      );
      expect(models).toMatchObject({
        current_model: { model_id: "fake-pi-opus-4-8" },
      });

      // pi_session_id lives directly under the agent state path.
      const stateSessionFile = path.join(
        dir,
        "state",
        "tsk_pi",
        "pi_session_id",
      );
      await waitFor(() => existsSync(stateSessionFile));
      expect(readFileSync(stateSessionFile, "utf8").length).toBeGreaterThan(0);
    },
    E2E_TIMEOUT_MS,
  );

  it(
    "fails the agent when the binary is missing",
    async () => {
      const harness = new PiHarness({
        resolveBinaryPath: () => undefined,
        environmentFor: () => makeEnvironment(dir),
        initializationStrategyFor: () => "WORKTREE",
      });
      const messages: Record<string, unknown>[] = [];
      let exit: HarnessExitResult | undefined;
      const agentProcess = harness.launch({
        agent: AGENT,
        workingDirectory: dir,
      });
      agentProcess.onMessage((m) => messages.push(m));
      agentProcess.onExit((r) => (exit = r));
      agentProcess.sendUserMessage({ message_id: "agm_u", text: "hello" });

      await waitFor(() => exit !== undefined);
      expect(messages.map((m) => m.object_type)).toEqual([
        "RequestStartedAgentMessage",
        "RequestFailureAgentMessage",
      ]);
      expect((exit?.error as { exception: string }).exception).toBe(
        "PiBinaryNotFoundError",
      );
    },
    E2E_TIMEOUT_MS,
  );
});
