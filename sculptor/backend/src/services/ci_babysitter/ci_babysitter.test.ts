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
import {
  type BabysitterDriver,
  type ResolvedBabysitterAgent,
} from "~/services/ci_babysitter/driver";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

function enableBabysitter(enabled: boolean): void {
  writeFileSync(
    configPath(),
    `[ci_babysitter]\nenabled = ${enabled ? "true" : "false"}\nretry_cap = 3\n`,
  );
}

// A driver that records every delivered workspace id and resolves to whatever
// `resolution` says — so the unit tests exercise the coordinator's policy
// (baseline, dedup, cap, pause, retire) without touching the agent service.
function stubDriver(
  dispatched: string[],
  resolution: ResolvedBabysitterAgent = { kind: "chat", agentType: "claude" },
): BabysitterDriver {
  return {
    resolve: () => resolution,
    deliver: (workspaceId) => dispatched.push(workspaceId),
  };
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

  // A failed-pipeline status carrying an explicit pipeline id (the edge the
  // classifier keys PIPELINE_FAILED on).
  const failed = (id: number): Record<string, unknown> => ({
    pr_state: "open",
    pipeline_status: "failed",
    pipeline_id: id,
  });

  it("is off by default — no retries unless enabled", () => {
    enableBabysitter(false);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(stubDriver(dispatched));
    coordinator.onPrStatus("ws_1", "prj_1", failed(1));
    expect(dispatched).toHaveLength(0);
    expect(coordinator.getStateSnapshot("ws_1")).toBeUndefined();
  });

  it("does not fire on the first poll (baseline), then fires on a new pipeline id", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(stubDriver(dispatched));
    coordinator.onPrStatus("ws_1", "prj_1", failed(100)); // baseline — no dispatch
    expect(dispatched).toHaveLength(0);
    coordinator.onPrStatus("ws_1", "prj_1", failed(101)); // changed id — fires
    expect(dispatched).toEqual(["ws_1"]);
  });

  it("retries up to the cap of 3, then retires", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(stubDriver(dispatched));
    for (const id of [1, 2, 3, 4, 5]) {
      coordinator.onPrStatus("ws_1", "prj_1", failed(id));
    }
    // id=1 is the baseline (no dispatch); ids 2,3,4 each fire; id=5 is past cap.
    expect(dispatched).toHaveLength(3);
    const view = coordinator.buildView("ws_1");
    expect(view.retryCount).toBe(3);
    expect(view.atCap).toBe(true);
    // Reaching the cap stops dispatching but is distinct from retirement, which
    // is reserved for a merged/closed MR.
    expect(view.retired).toBe(false);
  });

  it("does not retry while paused", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(stubDriver(dispatched));
    coordinator.onPrStatus("ws_1", "prj_1", failed(1)); // baseline
    coordinator.setPaused("ws_1", "prj_1", true);
    coordinator.onPrStatus("ws_1", "prj_1", failed(2)); // would fire, but paused
    expect(dispatched).toHaveLength(0);
  });

  it("is idempotent on a repeated pipeline id", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(stubDriver(dispatched));
    coordinator.onPrStatus("ws_1", "prj_1", failed(1)); // baseline
    coordinator.onPrStatus("ws_1", "prj_1", failed(2)); // fires
    coordinator.onPrStatus("ws_1", "prj_1", failed(2)); // same id — deduped
    expect(dispatched).toHaveLength(1);
  });

  it("fires once for a merge conflict on the first observation", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(stubDriver(dispatched));
    const conflict = { pr_state: "open", has_conflicts: true };
    coordinator.onPrStatus("ws_1", "prj_1", conflict);
    coordinator.onPrStatus("ws_1", "prj_1", conflict); // repeat — deduped
    expect(dispatched).toEqual(["ws_1"]);
  });

  it("retires (no further prompts) once the MR is merged", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(stubDriver(dispatched));
    coordinator.onPrStatus("ws_1", "prj_1", failed(1)); // baseline
    coordinator.onPrStatus("ws_1", "prj_1", { pr_state: "merged" });
    coordinator.onPrStatus("ws_1", "prj_1", failed(2)); // retired — no dispatch
    expect(dispatched).toHaveLength(0);
    expect(coordinator.buildView("ws_1").retired).toBe(true);
  });

  it("surfaces a persistent disabled reason from the driver", () => {
    enableBabysitter(true);
    const dispatched: string[] = [];
    const coordinator = new CIBabysitterCoordinator(
      stubDriver(dispatched, {
        kind: "disabled",
        reason: "can't drive this agent",
        transient: false,
      }),
    );
    coordinator.onPrStatus("ws_1", "prj_1", failed(1)); // baseline — creates state
    coordinator.onPrStatus("ws_1", "prj_1", failed(2)); // resolve → disabled
    expect(dispatched).toHaveLength(0);
    const view = coordinator.buildView("ws_1");
    expect(view.disabledReason).toBe("can't drive this agent");
    expect(view.disabledReasonIsTransient).toBe(false);
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
