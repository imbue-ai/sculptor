// Claude on-disk path resolution, shared by the harness (Task 5.3) and session
// resume (Task 5.4). Ports `harness.py`'s `compute_claude_jsonl_directory` /
// `_get_claude_config_dir` / `get_tasks_path`. Kept in its own module so both
// `harness.ts` and `session.ts` can import it without a cycle.

import { realpathSync } from "node:fs";
import path from "node:path";

import {
  CLAUDE_CONFIG_DIR_ENV_VAR,
  CLAUDE_DEFAULT_DIR_NAME,
  CLAUDE_PROJECTS_SUBDIRECTORY,
  CLAUDE_TASKS_SUBDIRECTORY,
} from "~/harness/claude/constants";

// Honor $CLAUDE_CONFIG_DIR (SCU-1295), falling back to <home>/.claude. An empty
// string is treated as unset, matching Claude Code's own resolution.
export function claudeConfigDir(
  home: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const custom = env[CLAUDE_CONFIG_DIR_ENV_VAR];
  return custom ? custom : path.join(home, CLAUDE_DEFAULT_DIR_NAME);
}

// Compute the Claude session-JSONL directory for a working directory. Claude
// sanitizes paths by replacing every non-alphanumeric character (except '-')
// with '-'. Mirrors `compute_claude_jsonl_directory`.
export function computeClaudeJsonlDirectory(
  home: string,
  workingDirectory: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const sanitized = workingDirectory.replace(/[^a-zA-Z0-9-]/g, "-");
  return path.join(
    claudeConfigDir(home, env),
    CLAUDE_PROJECTS_SUBDIRECTORY,
    sanitized,
  );
}

function resolveSymlink(p: string): string {
  try {
    return realpathSync(p);
  } catch {
    return p;
  }
}

// The session-file directory for an agent's working directory, resolving
// symlinks like the CLI does (on macOS /var -> /private/var). Mirrors
// `ClaudeCodeHarness.get_jsonl_path`.
export function resolveJsonlDirectory(
  home: string,
  workingDirectory: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  return computeClaudeJsonlDirectory(
    home,
    resolveSymlink(workingDirectory),
    env,
  );
}

// The per-task JSON store directory (`$CLAUDE_CONFIG_DIR/tasks/<session_id>`).
export function getTasksPath(
  home: string,
  sessionId: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  return path.join(
    claudeConfigDir(home, env),
    CLAUDE_TASKS_SUBDIRECTORY,
    sessionId,
  );
}
