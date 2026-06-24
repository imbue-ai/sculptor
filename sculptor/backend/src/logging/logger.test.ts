import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import { resolveLogLevel, serverLogFilePath, setupLogging } from "~/logging/logger";

describe("logging", () => {
  let root: string;
  let env: NodeJS.ProcessEnv;

  beforeEach(() => {
    root = mkdtempSync(path.join(tmpdir(), "sculptor-logs-"));
    env = { [SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG]: root } as NodeJS.ProcessEnv;
  });

  afterEach(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it("resolves the level from LOG_LEVEL, defaulting to debug", () => {
    expect(resolveLogLevel({} as NodeJS.ProcessEnv)).toBe("debug");
    expect(resolveLogLevel({ LOG_LEVEL: "INFO" } as NodeJS.ProcessEnv)).toBe("info");
  });

  it("writes a JSONL line to internal/logs/server/logs.jsonl and creates the server subdir", async () => {
    const logger = setupLogging(env);
    const file = serverLogFilePath(env);
    expect(file).toBe(path.join(root, "internal", "logs", "server", "logs.jsonl"));

    logger.info({ marker: "hello-log" }, "boot message");
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(existsSync(file)).toBe(true);
    const lines = readFileSync(file, "utf8").trim().split("\n");
    const parsed = lines.map((line) => JSON.parse(line) as Record<string, unknown>);
    const entry = parsed.find((record) => record.marker === "hello-log");
    expect(entry).toBeDefined();
    expect(entry?.msg).toBe("boot message");
  });

  it("drops log lines below the configured level", async () => {
    const logger = setupLogging({ ...env, LOG_LEVEL: "warn" });
    const file = serverLogFilePath(env);

    logger.info({ marker: "dropped" }, "below threshold");
    logger.warn({ marker: "kept" }, "at threshold");
    await new Promise((resolve) => setTimeout(resolve, 50));

    const content = readFileSync(file, "utf8");
    expect(content).toContain("kept");
    expect(content).not.toContain("dropped");
  });
});
