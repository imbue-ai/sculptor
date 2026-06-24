import { describe, expect, it } from "vitest";

import { EventBus } from "~/events/bus";
import { SCOPE_ALL_ONLY_EVENT_KINDS, type BusEvent } from "~/events/types";

describe("EventBus", () => {
  it("delivers events to subscribers in publish order", () => {
    const bus = new EventBus();
    const received: string[] = [];
    bus.subscribe((event) => received.push(event.kind));

    bus.publish({ kind: "agent_message", agentId: "tsk_1", message: { message_id: "m1" } });
    bus.publish({ kind: "agent_status", agentId: "tsk_1" });
    bus.publish({ kind: "workspace_branch", workspaceId: "ws_1" });

    expect(received).toEqual(["agent_message", "agent_status", "workspace_branch"]);
  });

  it("fans out to multiple subscribers and stops on unsubscribe", () => {
    const bus = new EventBus();
    const a: BusEvent[] = [];
    const b: BusEvent[] = [];
    const unsubscribeA = bus.subscribe((e) => a.push(e));
    bus.subscribe((e) => b.push(e));

    bus.publish({ kind: "dependencies_status", status: null });
    unsubscribeA();
    bus.publish({ kind: "pr_status", workspaceId: "ws_1" });

    expect(a.map((e) => e.kind)).toEqual(["dependencies_status"]);
    expect(b.map((e) => e.kind)).toEqual(["dependencies_status", "pr_status"]);
  });

  it("carries the scope ids needed for filtering", () => {
    const bus = new EventBus();
    let captured: BusEvent | undefined;
    bus.subscribe((e) => {
      captured = e;
    });
    bus.publish({ kind: "ui_open_file", workspaceId: "ws_9", projectId: "prj_1", action: {} });
    expect(captured).toMatchObject({ workspaceId: "ws_9", projectId: "prj_1" });
  });

  it("flags the ScopeAll-only event kinds", () => {
    expect(SCOPE_ALL_ONLY_EVENT_KINDS.has("data_model_change")).toBe(true);
    expect(SCOPE_ALL_ONLY_EVENT_KINDS.has("dependencies_status")).toBe(true);
    expect(SCOPE_ALL_ONLY_EVENT_KINDS.has("agent_message")).toBe(false);
  });
});
