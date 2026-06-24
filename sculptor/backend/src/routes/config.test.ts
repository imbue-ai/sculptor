import {
  mkdtempSync,
  rmSync,
  writeFileSync,
  mkdirSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import {
  SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG,
  configPath,
} from "~/config/sculptor_folder";
import { loadSettings, UserConfigSchema } from "~/config/settings";
import {
  toCamelKey,
  userConfigToWire,
  wirePartialToInternal,
} from "~/config/user_config";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm } from "~/db/orm";
import { createRepo } from "~/db/repositories";
import { UserConfigWireSchema } from "~/routes/config";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("UserConfig wire boundary", () => {
  it("wire schema keys are exactly the camelCase of the internal schema keys", () => {
    const internalKeys = Object.keys(UserConfigSchema.shape)
      .map(toCamelKey)
      .sort();
    const wireKeys = Object.keys(UserConfigWireSchema.shape).sort();
    expect(wireKeys).toEqual(internalKeys);
  });

  it("round-trips snake<->camel, treating keybindings keys as opaque data", () => {
    const internal = UserConfigSchema.parse({
      user_email: "a@b.co",
      keybindings: { some_custom_action: "ctrl+k" },
      pi: { api_key_env_var_names: ["ANTHROPIC_API_KEY"] },
      ci_babysitter: { retry_cap: 5 },
    });
    const wire = userConfigToWire(internal) as Record<string, unknown>;
    expect(wire.userEmail).toBe("a@b.co");
    expect(wire.isErrorReportingEnabled).toBe(false);
    // keybindings mapping keys are user data and must NOT be camelized.
    expect(wire.keybindings).toEqual({ some_custom_action: "ctrl+k" });
    expect((wire.pi as Record<string, unknown>).apiKeyEnvVarNames).toEqual([
      "ANTHROPIC_API_KEY",
    ]);
    expect((wire.ciBabysitter as Record<string, unknown>).retryCap).toBe(5);

    const back = wirePartialToInternal(wire);
    expect(back.user_email).toBe("a@b.co");
    expect(back.keybindings).toEqual({ some_custom_action: "ctrl+k" });
    expect((back.pi as Record<string, unknown>).api_key_env_var_names).toEqual([
      "ANTHROPIC_API_KEY",
    ]);
  });
});

describe("config / onboarding routes", () => {
  let dir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-config-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    // config/status probes git via the dependency service; raise the probe
    // timeout so concurrent-suite load can't trip the 5s default.
    process.env.SCULPTOR_DEP_PROBE_TIMEOUT_MS = "30000";
    closeDatabase();
    ensureSculptorFolderReady(process.env);
    runMigrations(getDatabase(), MIGRATIONS_FOLDER);
    app = buildApp();
    await app.ready();
  });

  afterEach(async () => {
    await app.close();
    closeDatabase();
    delete process.env.SCULPTOR_DEP_PROBE_TIMEOUT_MS;
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
  });

  it("status reports not-onboarded before any config exists", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/config/status",
    });
    expect(res.statusCode).toBe(200);
    // hasDependenciesPassing depends on the host's git/claude binaries, so assert
    // only the config-derived fields here.
    expect(res.json()).toMatchObject({
      hasEmail: false,
      hasPrivacyConsent: false,
      hasProject: false,
    });
    expect(typeof res.json().hasDependenciesPassing).toBe("boolean");
  });

  it("status reflects a project once one exists", async () => {
    createRepo(createOrm(getDatabase()), { objectId: "prj_1", name: "r" });
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/config/status",
    });
    expect(res.json().hasProject).toBe(true);
  });

  it("saving an email persists config.toml and returns camelCase TelemetryInfo", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/config/email",
      payload: {
        userEmail: "dev@example.com",
        fullName: "Dev",
        isTelemetryEnabled: true,
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.userConfig.userEmail).toBe("dev@example.com");
    expect(body.userConfig.isPrivacyPolicyConsented).toBe(true);
    expect(body.userConfig.isErrorReportingEnabled).toBe(true);
    expect(typeof body.sculptorExecutionInstanceId).toBe("string");

    // config.toml on disk is snake_case.
    expect(existsSync(configPath())).toBe(true);
    const onDisk = loadSettings(configPath());
    expect(onDisk.user_email).toBe("dev@example.com");
    expect(onDisk.is_telemetry_level_set).toBe(true);

    const status = await app.inject({
      method: "GET",
      url: "/api/v1/config/status",
    });
    expect(status.json()).toMatchObject({
      hasEmail: true,
      hasPrivacyConsent: true,
    });
  });

  it("skip_account records consent without an email", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/config/skip_account",
      payload: { isTelemetryEnabled: false },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.userConfig.userEmail).toBe("");
    expect(body.userConfig.isPrivacyPolicyConsented).toBe(true);
    expect(body.userConfig.isErrorReportingEnabled).toBe(false);
  });

  it("GET /config returns the current config in camelCase", async () => {
    const res = await app.inject({ method: "GET", url: "/api/v1/config" });
    expect(res.statusCode).toBe(200);
    expect(res.json().userEmail).toBe("");
    expect(res.json().updateChannel).toBe("STABLE");
  });

  it("PUT /config merges a field and rejects telemetry-flag changes", async () => {
    const ok = await app.inject({
      method: "PUT",
      url: "/api/v1/config",
      payload: { userConfig: { enableInPlaceWorkspaces: true } },
    });
    expect(ok.statusCode).toBe(200);
    expect(ok.json().enableInPlaceWorkspaces).toBe(true);

    // The default config has telemetry enabled, so flipping a flag is a real
    // change and must be rejected (only POST /config/telemetry may change it).
    const rejected = await app.inject({
      method: "PUT",
      url: "/api/v1/config",
      payload: { userConfig: { isErrorReportingEnabled: false } },
    });
    expect(rejected.statusCode).toBe(400);
  });

  it("telemetry endpoint flips the SDK flags", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/config/telemetry",
      payload: { enabled: true },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().isErrorReportingEnabled).toBe(true);
    expect(res.json().isProductAnalyticsEnabled).toBe(true);
    expect(res.json().isSessionRecordingEnabled).toBe(false);
  });

  it("complete returns 400 before the welcome step, 200 after", async () => {
    const tooEarly = await app.inject({
      method: "POST",
      url: "/api/v1/config/complete",
    });
    expect(tooEarly.statusCode).toBe(400);

    await app.inject({
      method: "POST",
      url: "/api/v1/config/skip_account",
      payload: {},
    });
    const completed = await app.inject({
      method: "POST",
      url: "/api/v1/config/complete",
    });
    expect(completed.statusCode).toBe(200);
  });

  it("telemetry_info falls back to the anonymous config before onboarding", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/telemetry_info",
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().userConfig.userEmail).toBe("");
    expect(res.json().userConfig.userId).not.toBe("");
  });

  it("env-var-names lists the global .env variable names", async () => {
    writeFileSync(
      path.join(dir, ".env"),
      "FOO=1\nexport BAR='x' # note\n# comment\nBAZ=qux\n",
    );
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/env-var-names",
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().globalVarNames).toEqual(["FOO", "BAR", "BAZ"]);
    expect(res.json().globalEnvPath).toContain(".env");
  });

  it("env-var-names includes per-project .env names", async () => {
    const projectDir = mkdtempSync(path.join(tmpdir(), "sculptor-proj-"));
    mkdirSync(path.join(projectDir, ".sculptor"), { recursive: true });
    writeFileSync(
      path.join(projectDir, ".sculptor", ".env"),
      "PROJECT_KEY=1\n",
    );
    createRepo(createOrm(getDatabase()), {
      objectId: "prj_env",
      name: "envproj",
      userGitRepoUrl: `file://${projectDir}`,
    });
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/env-var-names",
    });
    const projects = res.json().projects as {
      projectName: string;
      varNames: string[];
    }[];
    expect(projects.find((p) => p.projectName === "envproj")?.varNames).toEqual(
      ["PROJECT_KEY"],
    );
    rmSync(projectDir, { recursive: true, force: true });
  });
});
