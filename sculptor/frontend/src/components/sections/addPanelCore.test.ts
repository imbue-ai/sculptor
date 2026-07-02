import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UserConfig } from "~/api";
import { createAgentErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { diffScopeAtomFamily } from "~/pages/workspace/components/diffPanel/atoms.ts";

import {
  createAgentAndNavigate,
  createAgentInLocation,
  listAvailableLocations,
  normalizeRecentAgentType,
  openStaticPanelInLocation,
} from "./addPanelCore.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import { makeAgentPanelId } from "./registry/dynamicPanels.tsx";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import type { PanelId } from "./sectionTypes.ts";

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

describe("normalizeRecentAgentType", () => {
  it("falls back to Claude for a stored bare 'terminal' type", () => {
    // The new-workspace form's first-agent select can persist "terminal", but the
    // add-panel surfaces have no bare terminal AGENT row — terminal creation
    // belongs to the dedicated "New terminal" row.
    expect(normalizeRecentAgentType("terminal", true)).toBe("claude");
    expect(normalizeRecentAgentType("terminal", false)).toBe("claude");
  });

  it("falls back to Claude for 'pi' while the pi harness is disabled", () => {
    expect(normalizeRecentAgentType("pi", false)).toBe("claude");
  });

  it("keeps 'pi' while the pi harness is enabled", () => {
    expect(normalizeRecentAgentType("pi", true)).toBe("pi");
  });

  it("keeps Claude and registered terminal-agent types as-is", () => {
    expect(normalizeRecentAgentType("claude", false)).toBe("claude");
    expect(normalizeRecentAgentType("registered:my-agent", false)).toBe("registered:my-agent");
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

describe("createAgentInLocation pi gating", () => {
  it("falls back to Claude when a pi agent is requested while the pi harness is disabled", async () => {
    // Any create surface can hand in a remembered "pi" type from before the flag
    // was turned off; the core resolves the fallback so no caller has to.
    createWorkspaceAgentMock.mockResolvedValue({ data: { id: "task-pi" } });
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    // No user config → isPiAgentEnabledAtom resolves false.

    await createAgentInLocation(store, "center", { agentType: "pi" });

    expect(createWorkspaceAgentMock).toHaveBeenCalledTimes(1);
    expect(createWorkspaceAgentMock.mock.calls[0][0].body.agentType).toBe("claude");
  });

  it("keeps the pi type when the pi harness is enabled", async () => {
    createWorkspaceAgentMock.mockResolvedValue({ data: { id: "task-pi" } });
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(userConfigAtom, { enablePiAgent: true } as unknown as UserConfig);

    await createAgentInLocation(store, "center", { agentType: "pi" });

    expect(createWorkspaceAgentMock.mock.calls[0][0].body.agentType).toBe("pi");
  });
});

describe("createAgentAndNavigate", () => {
  it("navigates to the created agent on success", async () => {
    createWorkspaceAgentMock.mockResolvedValue({ data: { id: "task-nav" } });
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    const navigate = vi.fn();

    await createAgentAndNavigate(store, "center", { agentType: "claude" }, navigate);

    expect(navigate).toHaveBeenCalledWith("ws-test", "task-nav");
    expect(store.get(createAgentErrorToastAtom)).toBeNull();
  });

  it("surfaces the shared error toast (and does not navigate) when the create fails", async () => {
    createWorkspaceAgentMock.mockRejectedValue(new Error("boom"));
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    const navigate = vi.fn();

    await createAgentAndNavigate(store, "center", { agentType: "claude" }, navigate);

    expect(navigate).not.toHaveBeenCalled();
    expect(store.get(createAgentErrorToastAtom)).toMatchObject({ title: "Failed to create agent" });
  });
});

describe("openStaticPanelInLocation Review All scope", () => {
  const reviewAllId = "review-all" as PanelId;

  it("opens Review All on the 'All' (vs target branch) scope when newly placed", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });
    expect(store.get(diffScopeAtomFamily("ws-test"))).toBe("uncommitted");

    openStaticPanelInLocation(store, reviewAllId, "left");

    expect(store.get(diffScopeAtomFamily("ws-test"))).toBe("vs-target-branch");
    expect(store.get(workspaceLayoutAtom).placement[reviewAllId]).toBe("left");
  });

  it("does not stomp a scope the user picked while the panel is already open", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });
    openStaticPanelInLocation(store, reviewAllId, "left");

    // The user flips the open panel to Uncommitted; re-revealing the placed panel
    // must keep their choice.
    store.set(diffScopeAtomFamily("ws-test"), "uncommitted");
    openStaticPanelInLocation(store, reviewAllId, "left");

    expect(store.get(diffScopeAtomFamily("ws-test"))).toBe("uncommitted");
  });

  it("leaves the Review All scope alone when opening other panels", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });

    openStaticPanelInLocation(store, "files" as PanelId, "left");

    expect(store.get(diffScopeAtomFamily("ws-test"))).toBe("uncommitted");
  });
});
