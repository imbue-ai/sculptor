import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm, type Orm } from "~/db/orm";
import { createAgent, createRepo, createWorkspace, listAgentMessages } from "~/db/repositories";
import { ProjectionCache } from "~/projection/cache";
import { foldMessages } from "~/projection/message_conversion";
import { MessageWriter } from "~/runner/message_writer";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

function partial(id: string, index: number): Record<string, unknown> {
  return {
    object_type: "PartialResponseBlockAgentMessage",
    message_id: id,
    source: "AGENT",
    first_response_message_id: "agm_turn",
    start_index: 0,
    content: [{ object_type: "TextBlock", type: "text", text: `chunk ${index}` }],
  };
}

describe("MessageWriter coalescing", () => {
  let dir: string;
  let db: DatabaseConnection;
  let orm: Orm;
  let cache: ProjectionCache;
  let streamed: number;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-writer-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, MIGRATIONS_FOLDER);
    orm = createOrm(db);
    cache = new ProjectionCache();
    streamed = 0;
    createRepo(orm, { objectId: "prj_1", name: "r" });
    createWorkspace(orm, { objectId: "ws_1", projectId: "prj_1", description: "d", initializationStrategy: "WORKTREE" });
    createAgent(orm, { objectId: "tsk_1", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {} });
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("streams every chunk but writes far fewer partial rows than chunks", () => {
    // A fixed clock so flushing is count-driven, not time-driven.
    const writer = new MessageWriter({ orm, agentId: "tsk_1", cache, onStream: () => (streamed += 1), now: () => 0 });
    for (let i = 0; i < 100; i++) {
      writer.write(partial(`agm_${i}`, i));
    }
    // The warm cache + bus saw every chunk.
    expect(streamed).toBe(100);
    // But the DB has far fewer rows (coalesced every 20 chunks).
    const persisted = listAgentMessages(orm, "tsk_1", { includePartial: true });
    expect(persisted.length).toBeLessThanOrEqual(6);
    expect(persisted.length).toBeGreaterThan(0);
  });

  it("writes the finalized message once, flushes the buffered partial, and the cold re-fold matches live", () => {
    const writer = new MessageWriter({ orm, agentId: "tsk_1", cache, onStream: () => undefined, now: () => 0 });
    // A few partials that do not reach the flush threshold.
    writer.write(partial("agm_0", 0));
    writer.write(partial("agm_1", 1));
    // Finalize: the non-partial response replaces the streamed content.
    const finalMessage: Record<string, unknown> = {
      object_type: "ResponseBlockAgentMessage",
      message_id: "agm_final",
      source: "AGENT",
      content: [{ object_type: "TextBlock", type: "text", text: "final answer" }],
    };
    writer.write(finalMessage);

    const persisted = listAgentMessages(orm, "tsk_1", { includePartial: true });
    // The finalized row is present exactly once...
    expect(persisted.filter((m) => m.objectId === "agm_final")).toHaveLength(1);
    // ...and the buffered partial was flushed (agm_1, the latest before finalize).
    expect(persisted.map((m) => m.objectId)).toContain("agm_1");

    // The cold re-fold from the DB matches the live warm-cache state.
    const cold = foldMessages(persisted.map((m) => m.message));
    const live = cache.getChatMessages(orm, "tsk_1");
    expect(cold).toEqual(live);
  });
});
