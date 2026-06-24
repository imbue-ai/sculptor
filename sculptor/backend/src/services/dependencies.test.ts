import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ensureSculptorFolderReady } from "~/config/bootstrap";
import {
  getInternalFolder,
  SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG,
} from "~/config/sculptor_folder";
import { saveSettings, defaultUserConfig } from "~/config/settings";
import { DependencyService, isVersionInRange } from "~/services/dependencies";

describe("isVersionInRange", () => {
  it("gates Claude to its supported window and blocks 2.1.101", () => {
    expect(isVersionInRange("2.1.170", "CLAUDE")).toBe(true);
    expect(isVersionInRange("2.1.169", "CLAUDE")).toBe(false);
    expect(isVersionInRange("2.99.99", "CLAUDE")).toBe(true);
    expect(isVersionInRange("3.0.0", "CLAUDE")).toBe(false);
    expect(isVersionInRange("2.1.101", "CLAUDE")).toBe(false);
    expect(isVersionInRange("not-a-version", "CLAUDE")).toBe(false);
  });

  it("pins pi to its single supported version", () => {
    expect(isVersionInRange("0.78.0", "PI")).toBe(true);
    expect(isVersionInRange("0.79.0", "PI")).toBe(false);
  });

  it("treats git as unbounded", () => {
    expect(isVersionInRange("1.0.0", "GIT")).toBe(true);
  });
});

describe("DependencyService", () => {
  let dir: string;
  let previousFolder: string | undefined;

  function writeManagedClaude(version: string, versionOutput: string): void {
    const versionDir = path.join(
      getInternalFolder(),
      "dependencies",
      "claude",
      `version-${version}`,
    );
    mkdirSync(versionDir, { recursive: true });
    const binary = path.join(versionDir, "claude");
    writeFileSync(binary, `#!/bin/sh\necho '${versionOutput}'\n`);
    chmodSync(binary, 0o755);
  }

  beforeEach(() => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-deps-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    // The whole suite spawns many subprocesses concurrently; raise the probe
    // timeout so a trivially-fast stub can't trip the 5s default under load.
    process.env.SCULPTOR_DEP_PROBE_TIMEOUT_MS = "30000";
    ensureSculptorFolderReady(process.env);
    // Force claude into MANAGED mode regardless of the host's default override.
    saveSettings({
      ...defaultUserConfig(),
      dependency_paths: { git: null, claude: "MANAGED", pi: "MANAGED" },
    });
  });

  afterEach(() => {
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    delete process.env.SCULPTOR_DEP_PROBE_TIMEOUT_MS;
    rmSync(dir, { recursive: true, force: true });
  });

  it("detects a managed Claude binary and reports its version + range", async () => {
    writeManagedClaude("2.1.170", "2.1.170 (Claude Code)");
    const status = await new DependencyService().getStatus();
    expect(status.claude.installed).toBe(true);
    expect(status.claude.version).toBe("2.1.170");
    expect(status.claude.isVersionInRange).toBe(true);
    expect(status.claude.mode).toBe("MANAGED");
    expect(status.claude.managedVersion).toBe("2.1.170");
    expect(status.claude.versionRange).toEqual({
      minVersion: "2.1.170",
      maxVersion: "2.99.99",
      recommendedVersion: "2.1.170",
    });
  });

  it("flags an out-of-range managed Claude binary", async () => {
    writeManagedClaude("2.1.101", "2.1.101 (Claude Code)");
    const status = await new DependencyService().getStatus();
    expect(status.claude.installed).toBe(true);
    expect(status.claude.isVersionInRange).toBe(false);
  });

  it("reports Claude not installed when no managed binary exists", async () => {
    const status = await new DependencyService().getStatus();
    expect(status.claude.installed).toBe(false);
    expect(status.claude.isVersionInRange).toBeNull();
  });

  it("refuses to install or authenticate unmanaged/unsupported tools", async () => {
    const service = new DependencyService();
    const install = await service.installManaged("GIT");
    expect(install.success).toBe(false);
    expect(install.error).toContain("not supported");

    const auth = await service.startAuthLogin("GIT");
    expect(auth.success).toBe(false);
    expect(auth.error).toContain("not supported");
  });

  it("rejects a submitted auth code when no sign-in is in progress", async () => {
    const result = await new DependencyService().submitAuthCode(
      "CLAUDE",
      "abc",
    );
    expect(result.success).toBe(false);
    expect(result.error).toContain("No sign-in");
  });
});
