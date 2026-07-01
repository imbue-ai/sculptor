import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createAgentInLocation, listAvailableLocations } from "./addPanelCore.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import { makeAgentPanelId } from "./registry/dynamicPanels.tsx";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";

// createWorkspaceAgent hits the backend; stub it so we can assert the resulting layout
// placement deterministically.
const { createWorkspaceAgentMock } = vi.hoisted(() => ({ createWorkspaceAgentMock: vi.fn() }));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, createWorkspaceAgent: createWorkspaceAgentMock };
});

afterEach(() => {
  createWorkspaceAgentMock.mockReset();
});

describe("listAvailableLocations", () => {
  it("offers every section, including collapsed ones (adding a panel expands them)", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    // Only 'left' is expanded; right/bottom are collapsed. Center is always available.
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT, expanded: { left: true } });

    const subSections = listAvailableLocations(store).map((l) => l.subSection);
    expect(subSections).toContain("center");
    expect(subSections).toContain("left");
    // Collapsed sections must still be offered so a panel can be added to them.
    expect(subSections).toContain("right");
    expect(subSections).toContain("bottom");
  });
});

describe("createAgentInLocation placement", () => {
  it("places a new agent in the requested sub-section rather than forcing center", async () => {
    createWorkspaceAgentMock.mockResolvedValue({ data: { id: "task-right" } });
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });

    const taskId = await createAgentInLocation(store, "right", { agentType: "claude" });

    expect(taskId).toBe("task-right");
    const panelId = makeAgentPanelId("task-right");
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement[panelId]).toBe("right");
    expect(layout.order.right).toContain(panelId);
    expect(layout.activePanel.right).toBe(panelId);
    // It must NOT have been placed in center.
    expect(layout.order.center ?? []).not.toContain(panelId);
  });

  it("still places in center when center is requested (keybinding / command surfaces)", async () => {
    createWorkspaceAgentMock.mockResolvedValue({ data: { id: "task-center" } });
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });

    await createAgentInLocation(store, "center", { agentType: "claude" });

    const panelId = makeAgentPanelId("task-center");
    expect(store.get(workspaceLayoutAtom).placement[panelId]).toBe("center");
  });
});
