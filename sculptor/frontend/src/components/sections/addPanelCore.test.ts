import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TerminalAgentRegistration, UserConfig } from "~/api";
import { createAgentErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { diffScopeAtomFamily } from "~/pages/workspace/components/diffPanel/atoms.ts";

import {
  availableLocationsAtom,
  availableStaticPanelsAtom,
  buildAgentTypeOptions,
  createAgentAndNavigate,
  createAgentInLocation,
  normalizeRecentAgentType,
  openStaticPanelInLocation,
  recentAgentLabel,
  recentAgentTypeAtom,
  resolveStoredAgentType,
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

describe("resolveStoredAgentType", () => {
  it("passes 'pi' through (pi is always available)", () => {
    expect(resolveStoredAgentType("pi")).toBe("pi");
  });

  it("passes a bare 'terminal' through (a legitimate new-workspace first agent)", () => {
    expect(resolveStoredAgentType("terminal")).toBe("terminal");
  });

  it("keeps Claude and registered terminal-agent types as-is", () => {
    expect(resolveStoredAgentType("claude")).toBe("claude");
    expect(resolveStoredAgentType("registered:my-agent")).toBe("registered:my-agent");
  });
});

describe("recentAgentLabel", () => {
  const registration = { registrationId: "my-agent", displayName: "My Agent" } as TerminalAgentRegistration;

  it("labels the built-in types from AGENT_TYPE_LABELS", () => {
    expect(recentAgentLabel("claude", [])).toBe("Claude");
    expect(recentAgentLabel("pi", [])).toBe("pi");
  });

  it("labels a registered type from its registration's display name", () => {
    expect(recentAgentLabel("registered:my-agent", [registration])).toBe("My Agent");
  });

  it("falls back to the generic 'agent' when the registration is unknown", () => {
    // A remembered registration that has since been removed, or a caller (the
    // Cmd+K provider) that has no registrations list.
    expect(recentAgentLabel("registered:gone", [registration])).toBe("agent");
    expect(recentAgentLabel("registered:my-agent", [])).toBe("agent");
  });
});

describe("normalizeRecentAgentType", () => {
  it("falls back to Claude for a stored bare 'terminal' type", () => {
    // The new-workspace form's first-agent select can persist "terminal", but the
    // add-panel surfaces have no bare terminal AGENT row — terminal creation
    // belongs to the dedicated "New terminal" row.
    expect(normalizeRecentAgentType("terminal")).toBe("claude");
  });

  it("keeps 'pi' (pi is always available)", () => {
    expect(normalizeRecentAgentType("pi")).toBe("pi");
  });

  it("keeps Claude and registered terminal-agent types as-is", () => {
    expect(normalizeRecentAgentType("claude")).toBe("claude");
    expect(normalizeRecentAgentType("registered:my-agent")).toBe("registered:my-agent");
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

describe("createAgentInLocation pi agent", () => {
  it("creates a pi agent when a pi agent is requested (pi is always available)", async () => {
    createWorkspaceAgentMock.mockResolvedValue({ data: { id: "task-pi" } });
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");

    await createAgentInLocation(store, "center", { agentType: "pi" });

    expect(createWorkspaceAgentMock).toHaveBeenCalledTimes(1);
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

describe("recentAgentTypeAtom", () => {
  it("defaults to Claude when no type has been stored", () => {
    const store = createStore();
    expect(store.get(recentAgentTypeAtom)).toBe("claude");
  });

  it("normalizes a stored bare 'terminal' to Claude", () => {
    const store = createStore();
    store.set(userConfigAtom, { lastUsedAgentType: "terminal" } as unknown as UserConfig);
    expect(store.get(recentAgentTypeAtom)).toBe("claude");
  });

  it("keeps 'pi' (pi is always available), and registered types as-is", () => {
    const store = createStore();
    store.set(userConfigAtom, { lastUsedAgentType: "pi" } as unknown as UserConfig);
    expect(store.get(recentAgentTypeAtom)).toBe("pi");

    store.set(userConfigAtom, { lastUsedAgentType: "registered:my-agent" } as unknown as UserConfig);
    expect(store.get(recentAgentTypeAtom)).toBe("registered:my-agent");
  });
});

describe("availableStaticPanelsAtom", () => {
  it("lists the single-instance static panels that are not placed anywhere", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      placement: { files: "left" },
      order: { left: ["files"] },
    });

    const ids = store.get(availableStaticPanelsAtom).map((panel) => panel.id);
    expect(ids).not.toContain("files");
    expect(ids).toContain("changes");
    expect(ids).toContain("notes");
  });

  it("returns a reference-stable list across layout writes that do not change it", () => {
    // The menu content subscribes to this atom while open; the equality guard must
    // swallow unrelated layout writes (e.g. the active sub-section moving, a split
    // ratio drag) so the open menu does not re-render on them.
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      placement: { files: "left" },
      order: { left: ["files"] },
    });

    const first = store.get(availableStaticPanelsAtom);
    store.set(workspaceLayoutAtom, (prev) => ({ ...prev, activeSubSection: "left" }));
    expect(store.get(availableStaticPanelsAtom)).toBe(first);
  });

  it("recomputes when a panel opens or closes", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });

    const before = store.get(availableStaticPanelsAtom).map((panel) => panel.id);
    expect(before).toContain("files");

    openStaticPanelInLocation(store, "files" as PanelId, "left");
    const after = store.get(availableStaticPanelsAtom).map((panel) => panel.id);
    expect(after).not.toContain("files");
  });
});

describe("availableLocationsAtom", () => {
  it("lists the four plain sections for an unsplit layout", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });

    expect(store.get(availableLocationsAtom)).toEqual([
      { subSection: "left", label: "Left" },
      { subSection: "center", label: "Center" },
      { subSection: "right", label: "Right" },
      { subSection: "bottom", label: "Bottom" },
    ]);
  });

  it("disambiguates a split section's halves and stays reference-stable otherwise", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      splits: { center: { axis: "vertical", ratio: 0.5 } },
    });

    const locations = store.get(availableLocationsAtom);
    expect(locations).toContainEqual({ subSection: "center", label: "Center (primary)" });
    expect(locations).toContainEqual({ subSection: "center:secondary", label: "Center (secondary)" });

    // A placement-only write leaves the location list untouched.
    store.set(workspaceLayoutAtom, (prev) => ({ ...prev, placement: { files: "left" }, order: { left: ["files"] } }));
    expect(store.get(availableLocationsAtom)).toBe(locations);
  });
});

describe("buildAgentTypeOptions", () => {
  const registration = { registrationId: "my-agent", displayName: "My Agent" } as TerminalAgentRegistration;

  it("offers Claude and pi when nothing is registered (pi is always available)", () => {
    expect(buildAgentTypeOptions({ registrations: [] })).toEqual([
      { key: "claude", stored: "claude", agentType: "claude", registrationId: undefined, label: "Claude" },
      { key: "pi", stored: "pi", agentType: "pi", registrationId: undefined, label: "pi" },
    ]);
  });

  it("maps each registered terminal-agent program to a registered option", () => {
    const options = buildAgentTypeOptions({ registrations: [registration] });
    expect(options).toContainEqual({
      key: "registered:my-agent",
      stored: "registered:my-agent",
      agentType: "registered",
      registrationId: "my-agent",
      label: "My Agent",
    });
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
