import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ensureSculptorFolderReady, FORMAT_VERSION } from "~/config/bootstrap";
import { defaultUserConfig, loadSettings, saveSettings } from "~/config/settings";
import {
  configPath,
  databasePath,
  findRepoRoot,
  formatVersionPath,
  getSculptorFolder,
  getWorkspacesFolder,
  logsDir,
  resolveSculptorFolder,
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

  it("resolveSculptorFolder follows env > source-checkout > production, mirroring Python", () => {
    // 1. Override env wins.
    expect(resolveSculptorFolder({ [SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG]: "/x/y" }, "/repo", "/home")).toBe(
      path.resolve("/x/y"),
    );
    // 2. Running from a source checkout → <repo>/.dev_sculptor.
    expect(resolveSculptorFolder({}, "/repo", "/home")).toBe(path.join("/repo", ".dev_sculptor"));
    // 3. Packaged (no repo root) → ~/.sculptor.
    expect(resolveSculptorFolder({}, null, "/home")).toBe(path.join("/home", ".sculptor"));
    // An empty override string is ignored (falls through to source/production).
    expect(resolveSculptorFolder({ [SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG]: "" }, "/repo", "/home")).toBe(
      path.join("/repo", ".dev_sculptor"),
    );
  });

  it("findRepoRoot walks up to the nearest ancestor containing .git", () => {
    const tmp = mkdtempSync(path.join(tmpdir(), "sculptor-reporoot-"));
    try {
      const nested = path.join(tmp, "a", "b", "c");
      mkdirSync(nested, { recursive: true });
      // No .git in our temp tree yet — the walk doesn't stop at `tmp`.
      expect(findRepoRoot(nested)).not.toBe(tmp);
      // Create the marker at the temp root; now the walk stops there.
      mkdirSync(path.join(tmp, ".git"));
      expect(findRepoRoot(nested)).toBe(tmp);
      expect(findRepoRoot(tmp)).toBe(tmp);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("with no override, getSculptorFolder uses <repo>/.dev_sculptor when run from a checkout", () => {
    // The test runs inside the repo, so the source-checkout branch applies.
    const repoRoot = findRepoRoot(process.cwd());
    if (repoRoot === null) {
      return; // not a checkout (shouldn't happen in CI) — nothing to assert.
    }
    expect(getSculptorFolder({})).toBe(path.join(repoRoot, ".dev_sculptor"));
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
