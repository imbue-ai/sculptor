// Builds the `claude` CLI launch command, ported from
// `process_manager_utils.py:get_claude_command`. The harness runs the CLI via
// `bash -c "exec env IS_SANDBOX=1 <binary> …"` so signals reach claude directly
// (not bash) and the stdin control protocol stays open. Flag values track the
// upstream CLI compatibility window (REQ-COMPAT-020); the contract is fixed.

import {
  DISABLED_BUILTIN_TOOLS,
  FAKE_CLAUDE_MODEL_NAMES,
  MCP_SERVER_NAME,
  MODEL_SHORTNAME_MAP,
} from "~/harness/claude/constants";
import { ClaudeBinaryNotFoundError } from "~/harness/errors";

// Resolve the host `claude` binary, raising the specific, surfaced
// ClaudeBinaryNotFoundError when it is absent (REQ-INT-023) rather than a
// generic failure.
export function resolveClaudeBinary(
  resolver: () => string | undefined,
): string {
  const binaryPath = resolver();
  if (binaryPath === undefined) {
    throw new ClaudeBinaryNotFoundError();
  }
  return binaryPath;
}

// Single-quote a string for POSIX sh, matching Python's `shlex.quote`.
export function shellQuote(value: string): string {
  if (value === "") {
    return "''";
  }
  if (/^[a-zA-Z0-9_@%+=:,./-]+$/.test(value)) {
    return value;
  }
  return "'" + value.replace(/'/g, "'\\''") + "'";
}

export interface ClaudeCommandOptions {
  binaryPath: string;
  systemPrompt: string;
  sessionId?: string | null;
  // The CLI `--model` shortname (already mapped from the LLMModel), or null.
  modelShortname?: string | null;
  enableStreaming?: boolean;
  fastMode?: boolean;
  effort?: string | null;
  pluginDirs?: readonly string[];
  // Test-only: when set, launch the Python `fake_claude.py` CLI (`<python>
  // <script>`) instead of the real `claude` binary, mirroring
  // process_manager_utils.get_claude_command's `is_fake_claude` branch.
  fakeClaude?: { python: string; script: string } | null;
}

// Returns the full argv: `["bash", "-c", "<command string>"]`.
export function getClaudeCommand(options: ClaudeCommandOptions): string[] {
  const executable =
    options.fakeClaude != null
      ? `${shellQuote(options.fakeClaude.python)} ${shellQuote(options.fakeClaude.script)}`
      : `env IS_SANDBOX=1 ${shellQuote(options.binaryPath)}`;

  // `exec` replaces bash with claude so SIGTERM/SIGKILL reach claude. The MCP
  // config registers Sculptor's in-process SDK server; --disallowed-tools
  // suppresses the built-in AskUserQuestion / ExitPlanMode in favour of the
  // mcp__sculptor__* replacements.
  const mcpConfig = JSON.stringify({
    mcpServers: { [MCP_SERVER_NAME]: { type: "sdk", name: MCP_SERVER_NAME } },
  });
  let command =
    `exec ${executable} --dangerously-skip-permissions --permission-prompt-tool stdio` +
    ` --output-format=stream-json --verbose` +
    ` --input-format stream-json` +
    ` --include-hook-events` +
    ` --mcp-config ${shellQuote(mcpConfig)}` +
    ` --disallowed-tools ${shellQuote(DISABLED_BUILTIN_TOOLS.join(","))}`;

  if (options.enableStreaming) {
    command += " --include-partial-messages";
  }
  if (options.sessionId) {
    command += ` --resume ${shellQuote(options.sessionId)}`;
  }
  if (options.systemPrompt) {
    command += ` --append-system-prompt ${shellQuote(options.systemPrompt)}`;
  }
  if (options.modelShortname) {
    command += ` --model ${shellQuote(options.modelShortname)}`;
  }
  for (const pluginDir of options.pluginDirs ?? []) {
    command += ` --plugin-dir ${shellQuote(pluginDir)}`;
  }
  if (options.fastMode) {
    command += ` --settings ${shellQuote(JSON.stringify({ fastMode: true }))}`;
  }
  if (options.effort) {
    command += ` --effort ${shellQuote(options.effort)}`;
  }

  return ["bash", "-c", command];
}

// The stdin user message envelope (`_build_stdin_user_message`). session_id is
// empty so the CLI reuses the current session; --resume is passed separately.
export function buildStdinUserMessage(content: string): string {
  return (
    JSON.stringify({
      type: "user",
      session_id: "",
      message: { role: "user", content },
      parent_tool_use_id: null,
    }) + "\n"
  );
}

// The initialize control request that registers the PreCompact hook
// (`_build_initialize_control_request`). `requestId` is caller-supplied so the
// runtime stays free of `Math.random` for determinism in tests.
export function buildInitializeControlRequest(
  preCompactCallbackId: string,
  requestId: string,
): string {
  return (
    JSON.stringify({
      type: "control_request",
      request_id: requestId,
      request: {
        subtype: "initialize",
        hooks: {
          PreCompact: [
            { matcher: "auto", hookCallbackIds: [preCompactCallbackId] },
            { matcher: "manual", hookCallbackIds: [preCompactCallbackId] },
          ],
        },
      },
    }) + "\n"
  );
}

// The interrupt control request (`_send_interrupt_control_request`).
export function buildInterruptControlRequest(requestId: string): string {
  return (
    JSON.stringify({
      type: "control_request",
      request_id: requestId,
      request: { subtype: "interrupt" },
    }) + "\n"
  );
}

// Resolve the Python `fake_claude.py` launch command for a model wire value, or
// null for a real model / when the integration harness hasn't injected the
// script + interpreter paths. Shared by the agent harness (per-turn launch) and
// the /btw service (forked side-question), so both route FAKE_CLAUDE models to
// fake_claude instead of the real `claude` binary.
export function resolveFakeClaudeCommand(
  modelName: string | null,
): { python: string; script: string } | null {
  if (modelName === null || !FAKE_CLAUDE_MODEL_NAMES.has(modelName)) {
    return null;
  }
  const script = process.env.SCULPTOR_FAKE_CLAUDE_SCRIPT;
  const python = process.env.SCULPTOR_FAKE_CLAUDE_PYTHON;
  if (script === undefined || python === undefined) {
    return null;
  }
  return { python, script };
}

// Map the persisted LLMModel wire value to a `--model` shortname (omitted when
// unmapped, e.g. FAKE_CLAUDE — the CLI uses its default).
export function modelShortnameFor(
  modelName: string | null | undefined,
): string | null {
  if (!modelName) {
    return null;
  }
  return MODEL_SHORTNAME_MAP[modelName] ?? null;
}
