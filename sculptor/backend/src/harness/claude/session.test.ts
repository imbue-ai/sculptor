import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  isSessionIdValid,
  resolveSessionFilePath,
} from "~/harness/claude/session";

const WORKING_DIR = "/ws/code";
const SESSION_ID = "sess_abc";

describe("isSessionIdValid", () => {
  let configDir: string;
  let env: NodeJS.ProcessEnv;

  beforeEach(() => {
    configDir = mkdtempSync(path.join(tmpdir(), "sculptor-claude-cfg-"));
    env = { CLAUDE_CONFIG_DIR: configDir };
  });
  afterEach(() => {
    rmSync(configDir, { recursive: true, force: true });
  });

  const writeSession = (lines: string[]): void => {
    const file = resolveSessionFilePath(
      "/home/u",
      WORKING_DIR,
      SESSION_ID,
      env,
    );
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, lines.join("\n"));
  };

  const validate = (isSessionRunning: boolean): boolean =>
    isSessionIdValid({
      home: "/home/u",
      workingDirectory: WORKING_DIR,
      sessionId: SESSION_ID,
      isSessionRunning,
      env,
    });

  it("validates a session with a matching user/assistant line", () => {
    writeSession([
      JSON.stringify({
        type: "assistant",
        sessionId: SESSION_ID,
        message: { id: "a" },
      }),
    ]);
    expect(validate(false)).toBe(true);
  });

  it("returns false for a missing file", () => {
    expect(validate(false)).toBe(false);
  });

  it("returns false for an empty file or non-matching session id", () => {
    writeSession([""]);
    expect(validate(false)).toBe(false);
    writeSession([JSON.stringify({ type: "user", sessionId: "other" })]);
    expect(validate(false)).toBe(false);
  });

  it("tolerates a corrupt tail while running but is strict when not running", () => {
    // A malformed line precedes a valid one: while running it is skipped (the
    // valid prefix still validates); when not running it invalidates.
    writeSession([
      "{ corrupt",
      JSON.stringify({ type: "user", sessionId: SESSION_ID }),
    ]);
    expect(validate(true)).toBe(true);
    expect(validate(false)).toBe(false);
  });
});

describe("resolveSessionFilePath", () => {
  it("derives <jsonl-dir>/<session>.jsonl from the working directory", () => {
    expect(
      resolveSessionFilePath("/home/u", "/ws/code", "s1", {
        CLAUDE_CONFIG_DIR: "/cfg",
      }),
    ).toBe("/cfg/projects/-ws-code/s1.jsonl");
  });
});
