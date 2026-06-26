import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm, type Orm } from "~/db/orm";
import {
  appendAgentMessage,
  createAgent,
  createRepo,
  createWorkspace,
  getAgent,
  listAgentMessages,
} from "~/db/repositories";
import { eventBus } from "~/events";
import type { BusEvent } from "~/events/types";
import { projectionCache } from "~/projection/cache";
import { AgentRunner } from "~/runner";
import type { Harness, HarnessExitResult, HarnessProcess } from "~/runner/harness";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

class StubProcess implements HarnessProcess {
  private messageCb: ((m: Record<string, unknown>) => void) | undefined;
  private exitCb: ((r: HarnessExitResult) => void) | undefined;
  interrupted = false;
  stopped = false;
  readonly sent: Record<string, unknown>[] = [];

  onMessage(cb: (m: Record<string, unknown>) => void): void {
    this.messageCb = cb;
  }
  onExit(cb: (r: HarnessExitResult) => void): void {
    this.exitCb = cb;
  }
  sendUserMessage(m: Record<string, unknown>): void {
    this.sent.push(m);
  }
  interrupt(): void {
    this.interrupted = true;
  }
  stop(): void {
    this.stopped = true;
  }
  emit(m: Record<string, unknown>): void {
    this.messageCb?.(m);
  }
  finish(r: HarnessExitResult = {}): void {
    this.exitCb?.(r);
  }
}

class StubHarness implements Harness {
  last: StubProcess | undefined;
  launch(): HarnessProcess {
    this.last = new StubProcess();
    return this.last;
  }
}

describe("AgentRunner / AgentSupervisor", () => {
  let dir: string;
  let db: DatabaseConnection;
  let orm: Orm;
  let events: BusEvent[];
  let unsubscribe: () => void;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-runner-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, MIGRATIONS_FOLDER);
    orm = createOrm(db);
    projectionCache.clear();
    createRepo(orm, { objectId: "prj_1", name: "r" });
    createWorkspace(orm, { objectId: "ws_1", projectId: "prj_1", description: "d", initializationStrategy: "WORKTREE" });
    events = [];
    unsubscribe = eventBus.subscribe((e) => events.push(e));
  });

  afterEach(() => {
    unsubscribe();
    db.close();
    projectionCache.clear();
    rmSync(dir, { recursive: true, force: true });
  });

  it("supervises an agent: RUNNING, persists messages + events, then SUCCEEDED", () => {
    createAgent(orm, { objectId: "tsk_1", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {}, runState: "QUEUED" });
    const harness = new StubHarness();
    const runner = new AgentRunner({ orm, harnessFor: () => harness });

    runner.startAgent("tsk_1");
    expect(getAgent(orm, "tsk_1")?.runState).toBe("RUNNING");
    expect(events.some((e) => e.kind === "agent_status" && e.agentId === "tsk_1")).toBe(true);

    harness.last!.emit({ object_type: "ResponseBlockAgentMessage", message_id: "agm_1", source: "AGENT" });
    expect(listAgentMessages(orm, "tsk_1").map((m) => m.objectId)).toContain("agm_1");
    expect(events.some((e) => e.kind === "agent_message" && (e as { message?: { message_id?: string } }).message?.message_id === "agm_1")).toBe(true);

    harness.last!.finish();
    expect(getAgent(orm, "tsk_1")?.runState).toBe("SUCCEEDED");
  });

  it("marks FAILED when the harness exits with an error", () => {
    createAgent(orm, { objectId: "tsk_2", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {}, runState: "QUEUED" });
    const harness = new StubHarness();
    const runner = new AgentRunner({ orm, harnessFor: () => harness });
    runner.startAgent("tsk_2");
    harness.last!.finish({ error: { exception: "Boom", args: ["bad"] } });
    const agent = getAgent(orm, "tsk_2");
    expect(agent?.runState).toBe("FAILED");
    expect(agent?.error).toEqual({ exception: "Boom", args: ["bad"] });
  });

  it("stop() cancels the run and signals the harness", () => {
    createAgent(orm, { objectId: "tsk_3", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {}, runState: "QUEUED" });
    const harness = new StubHarness();
    const runner = new AgentRunner({ orm, harnessFor: () => harness });
    runner.startAgent("tsk_3");
    runner.interruptAgent("tsk_3");
    expect(harness.last!.interrupted).toBe(true);
    runner.stopAgent("tsk_3");
    expect(harness.last!.stopped).toBe(true);
    expect(getAgent(orm, "tsk_3")?.runState).toBe("CANCELLED");
  });

  it("resuperviseOnStartup restarts non-terminal agents and resets stuck RUNNING", async () => {
    createAgent(orm, { objectId: "tsk_run", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {}, runState: "RUNNING" });
    createAgent(orm, { objectId: "tsk_done", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {}, runState: "SUCCEEDED" });
    const harness = new StubHarness();
    const supervised: string[] = [];
    const runner = new AgentRunner({
      orm,
      harnessFor: (agent) => {
        supervised.push(agent.objectId);
        return harness;
      },
    });

    await runner.resuperviseOnStartup();

    // The stuck RUNNING agent was reset and re-supervised (now RUNNING again).
    expect(supervised).toEqual(["tsk_run"]);
    expect(getAgent(orm, "tsk_run")?.runState).toBe("RUNNING");
    // The terminal agent was not touched.
    expect(getAgent(orm, "tsk_done")?.runState).toBe("SUCCEEDED");
  });

  it("resuperviseOnStartup replays the in-flight turn and the queued follow-up", async () => {
    createAgent(orm, { objectId: "tsk_x", projectId: "prj_1", workspaceId: "ws_1", agentConfig: {}, runState: "RUNNING" });
    // An in-flight turn (started, never finished) followed by a queued follow-up.
    appendAgentMessage(orm, "tsk_x", { object_type: "ChatInputUserMessage", message_id: "msg_a", source: "USER", text: "first", model_name: "opus" });
    appendAgentMessage(orm, "tsk_x", { object_type: "RequestStartedAgentMessage", message_id: "rs_a", source: "AGENT", request_id: "msg_a" });
    appendAgentMessage(orm, "tsk_x", { object_type: "ChatInputUserMessage", message_id: "msg_b", source: "USER", text: "follow-up" });

    const harness = new StubHarness();
    const runner = new AgentRunner({ orm, harnessFor: () => harness });
    await runner.resuperviseOnStartup();

    const sent = harness.last!.sent;
    expect(sent).toHaveLength(2);
    // In-flight message resumes (continue, not a prompt replay), keyed to its id.
    expect(sent[0]).toMatchObject({ message_id: "msg_a", is_resume: true });
    expect(sent[0]).not.toHaveProperty("text");
    // The follow-up is re-dispatched fresh, after the resume.
    expect(sent[1]).toMatchObject({ message_id: "msg_b", text: "follow-up" });
  });
});
