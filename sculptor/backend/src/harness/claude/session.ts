// Claude session validation + corrupt-tail tolerance. Ports
// `process_manager_utils.py:is_session_id_valid`: a session is resumable iff its
// on-disk JSONL file holds at least one user/assistant line whose `sessionId`
// matches. A corrupt tail (malformed JSON line) is tolerated while the session
// is still running — the valid prefix still validates — but is treated as
// invalid once the session is no longer running.
//
// The session file lives where Claude re-derives it from the (unchanged)
// working directory; it is NEVER relocated (the migration preserves paths).

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { resolveJsonlDirectory } from "~/harness/claude/paths";

// `<jsonl-dir>/<session_id>.jsonl` — the file `claude --resume` reads.
export function resolveSessionFilePath(
  home: string,
  workingDirectory: string,
  sessionId: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  return path.join(
    resolveJsonlDirectory(home, workingDirectory, env),
    `${sessionId}.jsonl`,
  );
}

export interface SessionValidationOptions {
  home: string;
  workingDirectory: string;
  sessionId: string;
  // Whether the agent's CLI is currently running. While running, a malformed
  // tail line is skipped (the agent may still be writing); when not running, a
  // malformed line invalidates the session.
  isSessionRunning: boolean;
  env?: NodeJS.ProcessEnv;
}

function isResumableLine(line: string, sessionId: string): boolean {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    throw new SyntaxError("malformed line");
  }
  if (typeof parsed !== "object" || parsed === null) {
    return false;
  }
  const message = parsed as Record<string, unknown>;
  return (
    (message.type === "user" || message.type === "assistant") &&
    "sessionId" in message &&
    message.sessionId === sessionId
  );
}

// Validate a session id against its on-disk file. Mirrors `is_session_id_valid`.
export function isSessionIdValid(options: SessionValidationOptions): boolean {
  const filePath = resolveSessionFilePath(
    options.home,
    options.workingDirectory,
    options.sessionId,
    options.env,
  );
  if (!existsSync(filePath)) {
    return false;
  }
  let contents: string;
  try {
    contents = readFileSync(filePath, "utf8");
  } catch {
    return false;
  }
  for (const line of contents.trim().split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    try {
      if (isResumableLine(line, options.sessionId)) {
        return true;
      }
    } catch {
      // Malformed line: tolerated (skipped) while the session is running so a
      // corrupt tail resumes from the valid prefix; strict when not running.
      if (options.isSessionRunning) {
        continue;
      }
      return false;
    }
  }
  return false;
}
