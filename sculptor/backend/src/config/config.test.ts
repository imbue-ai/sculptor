import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ensureSculptorFolderReady, FORMAT_VERSION } from "~/config/bootstrap";
import { defaultUserConfig, loadSettings, saveSettings } from "~/config/settings";
import {
  configPath,
  databasePath,
  formatVersionPath,
  getSculptorFolder,
  getWorkspacesFolder,
  logsDir,
  SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG,
} from "~/config/sculptor_folder";

describe("sculptor folder resolution", () => {
  it("honors the override env flag and derives the documented subpaths", () => {
    const root = mkdtempSync(path.join(tmpdir(), "sculptor-folder-"));
    const env = { [SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG]: root } as NodeJS.ProcessEnv;
    try {
      expect(getSculptorFolder(env)).toBe(root);
      expect(databasePath(env)).toBe(path.join(root, "internal", "database.db"));
      expect(configPath(env)).toBe(path.join(root, "internal", "config.toml"));
      expect(logsDir(env)).toBe(path.join(root, "internal", "logs"));
      expect(formatVersionPath(env)).toBe(path.join(root, ".format_version"));
      expect(getWorkspacesFolder(env)).toBe(path.join(root, "workspaces"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});

describe("settings load/save", () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-settings-"));
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("fills defaults for a missing file", () => {
    const config = loadSettings(path.join(dir, "config.toml"));
    expect(config.min_free_disk_gb).toBe(2.0);
    expect(config.pr_default_target_branch).toBe("origin/main");
    expect(config.dependency_paths.claude).toBe("MANAGED");
    expect(config.default_effort_level).toBe("xhigh");
  });

  it("tolerates a legacy/unversioned config with extra fields and fills gaps", () => {
    const file = path.join(dir, "config.toml");
    writeFileSync(
      file,
      [
        'user_email = "dev@example.com"',
        "min_free_disk_gb = 5.0",
        "some_removed_legacy_field = 42",
        'claude_binary_mode = "PATH"',
      ].join("\n"),
    );
    const config = loadSettings(file);
    expect(config.user_email).toBe("dev@example.com");
    expect(config.min_free_disk_gb).toBe(5.0);
    // Unknown legacy fields are preserved (passthrough), not rejected.
    expect((config as Record<string, unknown>).some_removed_legacy_field).toBe(42);
    // Gaps are filled from defaults.
    expect(config.pr_polling_enabled).toBe(true);
  });

  it("round-trips through save and load", () => {
    const file = path.join(dir, "config.toml");
    const config = defaultUserConfig();
    config.user_email = "rt@example.com";
    config.min_free_disk_gb = 9.0;
    saveSettings(config, file);
    expect(existsSync(file)).toBe(true);
    const reloaded = loadSettings(file);
    expect(reloaded.user_email).toBe("rt@example.com");
    expect(reloaded.min_free_disk_gb).toBe(9.0);
  });
});

describe("folder bootstrap", () => {
  it("creates the dir tree and marker on a fresh folder and is a no-op afterward", () => {
    const root = mkdtempSync(path.join(tmpdir(), "sculptor-bootstrap-"));
    const env = { [SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG]: root } as NodeJS.ProcessEnv;
    try {
      ensureSculptorFolderReady(env);
      expect(existsSync(path.join(root, "internal"))).toBe(true);
      expect(existsSync(path.join(root, "workspaces"))).toBe(true);
      expect(readFileSync(formatVersionPath(env), "utf8")).toBe(`${FORMAT_VERSION}\n`);

      // Drop a sentinel file, then re-run: the existing folder is preserved.
      const sentinel = path.join(root, "internal", "sentinel.txt");
      writeFileSync(sentinel, "keep me");
      ensureSculptorFolderReady(env);
      expect(readFileSync(sentinel, "utf8")).toBe("keep me");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
