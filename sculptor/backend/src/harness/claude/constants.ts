// Claude harness constants. Ports the load-bearing literals from the Python
// backend's claude_code_sdk package:
//   - constants.py (TRANSIENT_ERROR_CODES)
//   - harness.py (ClaudeCodeHarness identity surface: session-dir name, MCP
//     server/tool names, the PreCompact hook callback id, the disabled built-in
//     tools, the model shortname map)
//   - agents/default/constants.py (MODEL_SHORTNAME_MAP, system-prompt content)
//   - mcp_server.py (_MCP_PROTOCOL_VERSION / _MCP_SERVER_VERSION / JSON-RPC codes)
//
// Flag values track the upstream Claude CLI compatibility window
// (REQ-COMPAT-020, recommended 2.1.170); the *contract* is what's fixed.

// https://docs.anthropic.com/en/api/errors — codes Sculptor treats as
// retryable (the turn raises an AgentTransientError rather than a hard failure).
export const TRANSIENT_ERROR_CODES: ReadonlySet<number> = new Set([
  429, 500, 529,
]);

// Claude Code's on-disk config layout. $CLAUDE_CONFIG_DIR overrides the base
// (SCU-1295); empty string is treated as unset, matching the CLI's own
// resolution. Session JSONLs live under <config-dir>/projects/./<sanitized-cwd>/.
export const CLAUDE_DEFAULT_DIR_NAME = ".claude";
export const CLAUDE_PROJECTS_SUBDIRECTORY = "projects/./";
export const CLAUDE_TASKS_SUBDIRECTORY = "tasks";
export const CLAUDE_CONFIG_DIR_ENV_VAR = "CLAUDE_CONFIG_DIR";

// The session-id state file the output processor writes under the agent's
// state path once the CLI reports its session id (used by Task 5.4 resume).
export const SESSION_ID_STATE_FILE_NAME = "session_id";
export const VALIDATED_SESSION_ID_STATE_FILE_NAME = "validated_session_id";

// The in-process MCP server Sculptor injects via --mcp-config, and its two
// tools that replace the disabled built-in AskUserQuestion / ExitPlanMode.
export const MCP_SERVER_NAME = "sculptor";
export const MCP_ASK_TOOL_NAME = "ask_user_question";
export const MCP_EXIT_PLAN_MODE_TOOL_NAME = "exit_plan_mode";

export const MCP_ASK_TOOL_FQN = `mcp__${MCP_SERVER_NAME}__${MCP_ASK_TOOL_NAME}`;
export const MCP_EXIT_PLAN_MODE_TOOL_FQN = `mcp__${MCP_SERVER_NAME}__${MCP_EXIT_PLAN_MODE_TOOL_NAME}`;

// The built-in tools Sculptor disables so it renders those interactions itself
// (load-bearing — see plan §Gotchas). Passed as a single comma-joined argument
// to --disallowed-tools.
export const DISABLED_BUILTIN_TOOLS: readonly string[] = [
  "AskUserQuestion",
  "ExitPlanMode",
];

// Tool-name recognition (harness.py _ASK_USER_QUESTION_TOOL_NAMES etc). The
// built-in names appear in persisted history even though the live CLI never
// emits them (it's disabled) — migrated/old sessions carry them.
export const ASK_USER_QUESTION_TOOL_NAMES: ReadonlySet<string> = new Set([
  "AskUserQuestion",
  MCP_ASK_TOOL_FQN,
]);
export const EXIT_PLAN_MODE_TOOL_NAMES: ReadonlySet<string> = new Set([
  "ExitPlanMode",
  MCP_EXIT_PLAN_MODE_TOOL_FQN,
]);
export const PLAN_FILE_WRITE_TOOL_NAMES: ReadonlySet<string> = new Set([
  "Write",
  "Edit",
  "MultiEdit",
]);
export const PLAN_FILE_SEGMENT = ".claude/plans/";

// The PreCompact lifecycle-hook callback id Sculptor registers via the stdin
// initialize control_request; the CLI references it in hook_callback events.
export const PRE_COMPACT_CALLBACK_ID = "sculptor_pre_compact";

// MCP protocol/version + JSON-RPC error codes (mcp_server.py).
export const MCP_PROTOCOL_VERSION = "2024-11-05";
export const MCP_SERVER_VERSION = "0.0.1";
export const JSONRPC_METHOD_NOT_FOUND = -32601;
export const JSONRPC_INVALID_PARAMS = -32602;
export const JSONRPC_INVALID_REQUEST = -32600;

// Maps the persisted LLMModel wire value (state/messages.py — hyphenated, e.g.
// "CLAUDE-4-SONNET") to the `--model` shortname the CLI expects. Mirrors
// agents/default/constants.py MODEL_SHORTNAME_MAP. A model with no mapping omits
// the --model flag (the CLI uses its own default).
export const MODEL_SHORTNAME_MAP: Readonly<Record<string, string>> = {
  "CLAUDE-4-OPUS": "opus[1m]",
  "CLAUDE-4-OPUS-200K": "opus",
  "CLAUDE-4-7-OPUS": "claude-opus-4-7[1m]",
  "CLAUDE-4-7-OPUS-200K": "claude-opus-4-7",
  "CLAUDE-4-6-OPUS": "claude-opus-4-6[1m]",
  "CLAUDE-4-6-OPUS-200K": "claude-opus-4-6",
  "CLAUDE-4-SONNET": "sonnet[1m]",
  "CLAUDE-4-SONNET-200K": "sonnet",
  "CLAUDE-4-HAIKU": "haiku",
  "CLAUDE-FABLE-5": "claude-fable-5",
};

// Default reasoning effort (process_manager.py self._effort = "xhigh").
export const DEFAULT_EFFORT = "xhigh";

// The Claude binary's tool-dependency key (Dependency.CLAUDE).
export const CLAUDE_BINARY_DEPENDENCY = "CLAUDE";

// File-change tools that produce a tracked diff (default/constants.py
// FILE_CHANGE_TOOL_NAMES).
export const FILE_CHANGE_TOOL_NAMES: ReadonlySet<string> = new Set([
  "Edit",
  "Write",
  "MultiEdit",
]);
