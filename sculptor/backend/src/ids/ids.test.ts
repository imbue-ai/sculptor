import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm, type Orm } from "~/db/orm";
import { createAgent, createRepo, softDeleteAgent } from "~/db/repositories";
import {
  AgentPrefixAmbiguousError,
  AgentPrefixNotFoundError,
  isAgentId,
  newAgentId,
  newWorkspaceId,
  parseAgentId,
  parseId,
  resolveAgentByPrefix,
  TypeIdPrefixMismatchError,
} from "~/ids";

describe("id minting and parsing", () => {
  it("mints prefixed typeids", () => {
    expect(newAgentId()).toMatch(/^agt_[0-9a-z]{26}$/);
    expect(newWorkspaceId()).toMatch(/^ws_[0-9a-z]{26}$/);
  });

  it("parseAgentId accepts both agt_ and tsk_ and rejects garbage", () => {
    const agt = newAgentId();
    expect(parseAgentId(agt)).toBe(agt);
    // A legacy tsk_ id with a valid suffix is accepted.
    const legacy = agt.replace(/^agt_/, "tsk_");
    expect(parseAgentId(legacy)).toBe(legacy);
    expect(isAgentId(legacy)).toBe(true);

    expect(() => parseAgentId("not-an-id")).toThrow(TypeIdPrefixMismatchError);
    expect(() => parseAgentId(newWorkspaceId())).toThrow(TypeIdPrefixMismatchError);
    expect(isAgentId(newWorkspaceId())).toBe(false);
  });

  it("parseId validates a specific prefix", () => {
    const ws = newWorkspaceId();
    expect(parseId("ws", ws)).toBe(ws);
    expect(() => parseId("agt", ws)).toThrow(TypeIdPrefixMismatchError);
  });
});

describe("resolveAgentByPrefix", () => {
  let dir: string;
  let db: DatabaseConnection;
  let orm: Orm;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-ids-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, path.resolve(process.cwd(), "drizzle"));
    orm = createOrm(db);
    createRepo(orm, { objectId: "prj_1", name: "r" });
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("resolves a unique prefix and handles not-found / ambiguous like Python", () => {
    createAgent(orm, { objectId: "tsk_aaa111", projectId: "prj_1", agentConfig: {} });
    createAgent(orm, { objectId: "agt_bbb222", projectId: "prj_1", agentConfig: {} });

    // Unique prefix (across both legacy and new prefixes).
    expect(resolveAgentByPrefix(orm, "tsk_aaa")).toBe("tsk_aaa111");
    expect(resolveAgentByPrefix(orm, "agt_")).toBe("agt_bbb222");

    // No match -> 404-equivalent error.
    expect(() => resolveAgentByPrefix(orm, "zzz")).toThrow(AgentPrefixNotFoundError);

    // Ambiguous -> 409-equivalent error.
    createAgent(orm, { objectId: "tsk_aaa999", projectId: "prj_1", agentConfig: {} });
    expect(() => resolveAgentByPrefix(orm, "tsk_aaa")).toThrow(AgentPrefixAmbiguousError);

    // Soft-deleted agents are excluded from prefix resolution.
    softDeleteAgent(orm, "tsk_aaa999");
    expect(resolveAgentByPrefix(orm, "tsk_aaa")).toBe("tsk_aaa111");
  });
});
