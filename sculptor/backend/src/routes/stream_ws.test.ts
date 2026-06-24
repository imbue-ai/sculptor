import { mkdtempSync, rmSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { WebSocket } from "ws";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm } from "~/db/orm";
import { createAgent, createRepo, createWorkspace } from "~/db/repositories";
import { eventBus } from "~/events";
import { projectionCache } from "~/projection/cache";
import type { StreamingUpdate } from "~/projection/streaming_update_types";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

interface Connection {
  socket: WebSocket;
  next(): Promise<StreamingUpdate>;
  pending(): number;
}

// Buffers messages from connection time so the snapshot can never be missed
// in the window between "open" and a "message" listener being attached.
function connect(port: number, scope?: string): Promise<Connection> {
  const query = scope === undefined ? "" : `?scope=${encodeURIComponent(scope)}`;
  const socket = new WebSocket(`ws://127.0.0.1:${port}/api/v1/stream/ws${query}`);
  const queue: StreamingUpdate[] = [];
  const waiters: ((update: StreamingUpdate) => void)[] = [];
  socket.on("message", (data: Buffer) => {
    const update = JSON.parse(data.toString()) as StreamingUpdate;
    const waiter = waiters.shift();
    if (waiter !== undefined) {
      waiter(update);
    } else {
      queue.push(update);
    }
  });
  return new Promise((resolve, reject) => {
    socket.once("error", reject);
    socket.once("open", () => {
      resolve({
        socket,
        next: () =>
          new Promise<StreamingUpdate>((res) => {
            const queued = queue.shift();
            if (queued !== undefined) {
              res(queued);
            } else {
              waiters.push(res);
            }
          }),
        pending: () => queue.length,
      });
    });
  });
}

describe("/api/v1/stream/ws", () => {
  let dir: string;
  let app: FastifyInstance | undefined;
  let port: number;
  let previousFolder: string | undefined;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-ws-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    closeDatabase();
    projectionCache.clear();
    ensureSculptorFolderReady(process.env);

    const db = getDatabase();
    runMigrations(db, MIGRATIONS_FOLDER);
    const orm = createOrm(db);
    createRepo(orm, { objectId: "prj_1", name: "r" });
    createWorkspace(orm, { objectId: "ws_1", projectId: "prj_1", description: "d", initializationStrategy: "WORKTREE" });
    createAgent(orm, { objectId: "tsk_1", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {} });

    app = buildApp();
    await app.ready();
    await app.listen({ port: 0, host: "127.0.0.1" });
    port = (app.server.address() as AddressInfo).port;
  });

  afterEach(async () => {
    await app?.close();
    closeDatabase();
    projectionCache.clear();
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
  });

  it("sends a full snapshot on connect, then a narrowed delta", async () => {
    const conn = await connect(port);
    try {
      const snapshot = await conn.next();
      expect(Object.keys(snapshot.task_views_by_task_id)).toContain("tsk_1");
      expect(snapshot.user_update.projects.map((p) => p.object_id)).toContain("prj_1");

      eventBus.publish({
        kind: "agent_message",
        agentId: "tsk_1",
        workspaceId: "ws_1",
        message: { object_type: "ChatInputUserMessage", message_id: "agm_1", source: "USER" },
      });
      const delta = await conn.next();
      expect(Object.keys(delta.task_update_by_task_id)).toContain("tsk_1");
    } finally {
      conn.socket.close();
    }
  });

  it("scopes to an agent: a different agent's events are not delivered", async () => {
    const conn = await connect(port, "agent:tsk_1");
    try {
      const snapshot = await conn.next();
      expect(Object.keys(snapshot.task_views_by_task_id)).toEqual(["tsk_1"]);
      expect(snapshot.user_update.projects).toEqual([]);

      eventBus.publish({ kind: "agent_status", agentId: "tsk_other", workspaceId: "ws_other" });
      await new Promise((resolve) => setTimeout(resolve, 100));
      expect(conn.pending()).toBe(0);
    } finally {
      conn.socket.close();
    }
  });

  it("rejects a WS without a valid session token (close 4401)", async () => {
    process.env.SESSION_TOKEN = "the-token";
    const socket = new WebSocket(`ws://127.0.0.1:${port}/api/v1/stream/ws`);
    const closeCode = await new Promise<number>((resolve, reject) => {
      socket.once("close", (code: number) => resolve(code));
      socket.once("error", reject);
    });
    expect(closeCode).toBe(4401);
  });
});
