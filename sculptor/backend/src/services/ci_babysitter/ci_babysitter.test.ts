import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { configPath } from "~/config/sculptor_folder";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { CIBabysitterCoordinator } from "~/services/ci_babysitter/coordinator";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

function enableBabysitter(enabled: boolean): void {
  writeFileSync(
    configPath(),
    `[ci_babysitter]\nenabled = ${enabled ? "true" : "false"}\nretry_cap = 3\n`,
  );
}

describe("CI babysitter", () => {
  let dir: string;
  let previousFolder: string | undefined;

  beforeEach(() => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-cibaby-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    ensureSculptorFolderReady(process.env);
  });

  afterEach(() => {
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
  });

  const failed = (pipelineId: number): Record<string, unknown> => ({
    pipeline_status: "failed",
    pipeline_id: pipelineId,
  });

  it("is off by default — no retries unless enabled", () => {
    enableBabysitter(false);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator((wsId) =>
      dispatched.push(wsId),
    );
    coordinator.onPrStatus("ws_1", "prj_1", failed(1));
    expect(dispatched).toHaveLength(0);
    expect(coordinator.getStateSnapshot("ws_1")).toBeUndefined();
  });

  it("retries up to the cap of 3, then retires", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator((wsId) =>
      dispatched.push(wsId),
    );
    for (const id of [1, 2, 3, 4, 5]) {
      coordinator.onPrStatus("ws_1", "prj_1", failed(id));
    }
    expect(dispatched).toHaveLength(3);
    const view = coordinator.buildView("ws_1");
    expect(view.retryCount).toBe(3);
    expect(view.atCap).toBe(true);
    expect(view.retired).toBe(true);
  });

  it("does not retry while paused", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator((wsId) =>
      dispatched.push(wsId),
    );
    coordinator.setPaused("ws_1", "prj_1", true);
    coordinator.onPrStatus("ws_1", "prj_1", failed(1));
    expect(dispatched).toHaveLength(0);
  });

  it("is idempotent on a repeated pipeline id", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator((wsId) =>
      dispatched.push(wsId),
    );
    coordinator.onPrStatus("ws_1", "prj_1", failed(1));
    coordinator.onPrStatus("ws_1", "prj_1", failed(1));
    expect(dispatched).toHaveLength(1);
  });

  describe("endpoints", () => {
    let app: FastifyInstance;

    beforeEach(async () => {
      closeDatabase();
      runMigrations(getDatabase(), MIGRATIONS_FOLDER);
      app = buildApp();
      await app.ready();
    });

    afterEach(async () => {
      await app.close();
      closeDatabase();
    });

    it("returns the default-off view and toggles pause", async () => {
      const status = await app.inject({
        method: "GET",
        url: "/api/v1/workspaces/ws_9/ci_babysitter",
      });
      expect(status.json()).toMatchObject({
        paused: false,
        retryCount: 0,
        retryCap: 3,
        atCap: false,
      });

      const pause = await app.inject({
        method: "POST",
        url: "/api/v1/workspaces/ws_9/ci_babysitter/pause",
        payload: { paused: true },
      });
      expect(pause.json().paused).toBe(true);
    });
  });
});
