import { beforeEach, describe, expect, it, vi } from "vitest";

import { TaskStatus } from "~/api";
import {
  isUnreadOverrideActive,
  resetUnreadOverridesForTesting,
  setUnreadOverride,
} from "~/common/state/atoms/unreadOverrides.ts";

import type { DynamicAgentInput } from "./dynamicPanels.tsx";
import { deriveDynamicPanels, makeAgentPanelId } from "./dynamicPanels.tsx";
import { panelDefinitionByIdAtom } from "./panelRegistry.ts";

const UPDATED_AT = "2024-01-01T00:00:00Z";
const LATER_UPDATED_AT = "2024-01-01T00:05:00Z";

const createAgentInput = (overrides: Partial<DynamicAgentInput> = {}): DynamicAgentInput => ({
  taskId: "task-1",
  displayName: "Agent 1",
  status: TaskStatus.READY,
  // Read after the last update, so the base dot derivation reads as "read".
  lastReadAt: "2024-01-01T00:01:00Z",
  updatedAt: UPDATED_AT,
  ...overrides,
});

beforeEach(() => {
  resetUnreadOverridesForTesting();
});

describe("deriveDynamicPanels dot status with the unread override", () => {
  it("derives 'read' for a seen agent with no override", () => {
    const [definition] = deriveDynamicPanels([createAgentInput()], []);
    expect(definition.dotStatus).toBe("read");
  });

  it("forces 'unread' while the override is active, even with a read-looking lastReadAt", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    const [definition] = deriveDynamicPanels([createAgentInput()], []);
    expect(definition.dotStatus).toBe("unread");
  });

  it("falls back to the base derivation once a new turn expires the override", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    // The new turn advances updatedAt past lastReadAt, so the base derivation
    // already reads as unread on its own.
    const [definition] = deriveDynamicPanels([createAgentInput({ updatedAt: LATER_UPDATED_AT })], []);
    expect(definition.dotStatus).toBe("unread");
  });

  it("keeps activity dots (running) ahead of the override", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    const [definition] = deriveDynamicPanels([createAgentInput({ status: TaskStatus.RUNNING })], []);
    expect(definition.dotStatus).toBe("running");
  });

  it("clears a deleted agent's override when its panel is evicted", () => {
    setUnreadOverride("task-1", UPDATED_AT);
    // Derive once so the agent's component is cached, then again without the
    // agent so the eviction path runs.
    deriveDynamicPanels([createAgentInput()], []);
    deriveDynamicPanels([], []);
    expect(isUnreadOverrideActive("task-1", UPDATED_AT)).toBe(false);
  });

  it("evicts the per-id definition slice when its agent disappears", () => {
    // The definition family is keyed by panel id, so a deleted agent's entry must
    // be removed with its component — otherwise the family grows forever. A fresh
    // atom instance for the same id proves the old entry was dropped.
    deriveDynamicPanels([createAgentInput()], []);
    const whileLive = panelDefinitionByIdAtom(makeAgentPanelId("task-1"));
    deriveDynamicPanels([], []);
    expect(panelDefinitionByIdAtom(makeAgentPanelId("task-1"))).not.toBe(whileLive);
  });
});

describe("agent tab context menu", () => {
  it("offers 'Mark as unread' first and invokes the supplied callback", () => {
    const onMarkUnread = vi.fn();
    const [definition] = deriveDynamicPanels([createAgentInput({ onMarkUnread })], []);

    const [markUnreadItem] = definition.contextMenuActions ?? [];
    expect(markUnreadItem.label).toBe("Mark as unread");
    markUnreadItem.action();
    expect(onMarkUnread).toHaveBeenCalledTimes(1);
  });

  it("builds the agent panel id the tab is keyed by", () => {
    const [definition] = deriveDynamicPanels([createAgentInput()], []);
    expect(definition.id).toBe(makeAgentPanelId("task-1"));
  });
});
