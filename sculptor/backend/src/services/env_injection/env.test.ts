import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import {
  globalEnvVarNames,
  projectEnvVarNames,
  resolveEnv,
} from "~/services/env_injection/env";

describe("env injection (REQ-INT-050 per-repo over global)", () => {
  let dir: string;
  let repoDir: string;
  let previousFolder: string | undefined;

  beforeEach(() => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-env-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    ensureSculptorFolderReady(process.env);
    writeFileSync(
      path.join(dir, ".env"),
      "SHARED=global_value\nGLOBAL_ONLY=g\n",
    );
    repoDir = mkdtempSync(path.join(tmpdir(), "sculptor-repo-"));
    mkdirSync(path.join(repoDir, ".sculptor"), { recursive: true });
    writeFileSync(
      path.join(repoDir, ".sculptor", ".env"),
      "SHARED=repo_value\nREPO_ONLY=r\n",
    );
  });

  afterEach(() => {
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
    rmSync(repoDir, { recursive: true, force: true });
  });

  it("resolves per-repo over global, passing global-only vars through", () => {
    const env = resolveEnv(repoDir);
    expect(env.SHARED).toBe("repo_value");
    expect(env.GLOBAL_ONLY).toBe("g");
    expect(env.REPO_ONLY).toBe("r");
  });

  it("falls back to the global set when there is no repo path", () => {
    const env = resolveEnv(null);
    expect(env.SHARED).toBe("global_value");
    expect(env.REPO_ONLY).toBeUndefined();
  });

  it("surfaces names only (never values)", () => {
    expect(globalEnvVarNames().sort()).toEqual(["GLOBAL_ONLY", "SHARED"]);
    expect(projectEnvVarNames(repoDir).sort()).toEqual(["REPO_ONLY", "SHARED"]);
  });
});
