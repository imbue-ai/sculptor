import { createStore } from "jotai";
import { Puzzle } from "lucide-react";
import type { ComponentType } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { TaskStatus } from "~/api";

import { EMPTY_WORKSPACE_LAYOUT } from "../persistence/types.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "../sectionAtoms.ts";
import type { DynamicAgentInput } from "./dynamicPanels.tsx";
import { deriveDynamicPanels } from "./dynamicPanels.tsx";
import {
  activePanelComponentInSubSectionAtom,
  buildPluginPanelDefinitions,
  buildStaticPanelDefinitions,
  isMultiInstanceKind,
  panelRegistriesEqual,
  panelRegistryAtom,
  registerPanelComponent,
  resolvedActivePanelIdInSubSectionAtom,
} from "./panelRegistry.ts";

// A minimal agent input with the fields the status dot + diagnostics derivation reads.
const makeAgent = (overrides: Partial<DynamicAgentInput> & Pick<DynamicAgentInput, "taskId">): DynamicAgentInput => ({
  displayName: "Agent 1",
  status: TaskStatus.READY,
  lastReadAt: "2024-01-01T00:00:00Z",
  updatedAt: "2024-01-01T00:00:00Z",
  ...overrides,
});

beforeEach(() => {
  localStorage.clear();
});

describe("static panel registry", () => {
  it("contains the eight static panels with correct default sections", () => {
    const defs = buildStaticPanelDefinitions();
    expect(defs.map((d) => d.id)).toEqual([
      "files",
      "changes",
      "commits",
      "review-all",
      "actions",
      "skills",
      "browser",
      "notes",
    ]);
    const byId = Object.fromEntries(defs.map((d) => [d.id, d]));
    expect(byId.files.defaultSection).toBe("left");
    expect(byId.changes.defaultSection).toBe("left");
    expect(byId.commits.defaultSection).toBe("left");
    expect(byId.actions.defaultSection).toBe("right");
    expect(byId.skills.defaultSection).toBe("right");
    expect(byId.notes.defaultSection).toBe("right");
    expect(byId["review-all"].defaultSection).toBeUndefined();
    expect(byId.browser.defaultSection).toBeUndefined();
    expect(defs.every((d) => d.kind === "static")).toBe(true);
  });

  it("has no enable/disable flags on a definition", () => {
    const def = buildStaticPanelDefinitions()[0];
    expect(def).not.toHaveProperty("enabled");
    expect(def).not.toHaveProperty("defaultEnabled");
    expect(def).not.toHaveProperty("isBuiltin");
  });

  it("marks only agent/terminal as multi-instance", () => {
    expect(isMultiInstanceKind("static")).toBe(false);
    expect(isMultiInstanceKind("agent")).toBe(true);
    expect(isMultiInstanceKind("terminal")).toBe(true);
  });
});

describe("dynamic panel derivation", () => {
  it("derives agent/terminal definitions with the right ids and defaults", () => {
    const defs = deriveDynamicPanels(
      [makeAgent({ taskId: "t1", displayName: "Agent 1" })],
      [{ workspaceId: "ws1", index: 0, displayName: "Terminal 1" }],
    );
    expect(defs.map((d) => d.id)).toEqual(["agent:t1", "terminal:ws1:0"]);
    expect(defs[0].kind).toBe("agent");
    expect(defs[0].defaultSection).toBe("center");
    expect(defs[1].kind).toBe("terminal");
    expect(defs[1].defaultSection).toBe("bottom");
  });

  it("gives an agent a status dot and diagnostics context actions", () => {
    const [agentDef] = deriveDynamicPanels(
      [makeAgent({ taskId: "t1", displayName: "Agent 1", diagnostics: { sessionId: null } })],
      [],
    );
    // READY with lastReadAt == updatedAt derives the calm "read" dot.
    expect(agentDef.dotStatus).toBe("read");
    const actionLabels = (agentDef.contextMenuActions ?? []).map((a) => a.label);
    expect(actionLabels).toContain("Copy agent id");
    expect(actionLabels).toContain("Copy claude session id");
    // Session id action is disabled until a session exists.
    const copySession = agentDef.contextMenuActions?.find((a) => a.label === "Copy claude session id");
    expect(copySession?.disabled).toBe(true);
  });

  it("wires the agent close button to the supplied delete callback", () => {
    let didRequestClose = false;
    const [agentDef] = deriveDynamicPanels(
      [makeAgent({ taskId: "t1", onRequestClose: () => (didRequestClose = true) })],
      [],
    );
    agentDef.onRequestClose?.();
    expect(didRequestClose).toBe(true);
  });

  it("caches the component reference per id across registry rebuilds", () => {
    const first = deriveDynamicPanels([makeAgent({ taskId: "stable", displayName: "x" })], []);
    const second = deriveDynamicPanels([makeAgent({ taskId: "stable", displayName: "x renamed" })], []);
    expect(first[0].component).toBe(second[0].component);
  });

  it("evicts the cached component when its task disappears", () => {
    const first = deriveDynamicPanels([makeAgent({ taskId: "evict-me", displayName: "x" })], []);
    deriveDynamicPanels([makeAgent({ taskId: "other", displayName: "y" })], []);
    const recreated = deriveDynamicPanels([makeAgent({ taskId: "evict-me", displayName: "x" })], []);
    expect(first[0].component).not.toBe(recreated[0].component);
  });
});

describe("panelRegistriesEqual", () => {
  it("treats a rebuilt registry with unchanged inputs as equal despite fresh objects", () => {
    const terminal = { workspaceId: "ws1", index: 0, displayName: "Terminal 1" };
    const first = deriveDynamicPanels([makeAgent({ taskId: "t1" })], [terminal]);
    // A rebuild produces new definition objects and new callback closures; only the
    // render-relevant fields are compared, so the registries still count as equal.
    const second = deriveDynamicPanels([makeAgent({ taskId: "t1" })], [terminal]);
    expect(second).not.toBe(first);
    expect(second[0].contextMenuActions).not.toBe(first[0].contextMenuActions);
    expect(panelRegistriesEqual(first, second)).toBe(true);
  });

  it("detects a dot-status change", () => {
    const before = deriveDynamicPanels([makeAgent({ taskId: "t1" })], []);
    const after = deriveDynamicPanels([makeAgent({ taskId: "t1", status: TaskStatus.RUNNING })], []);
    expect(panelRegistriesEqual(before, after)).toBe(false);
  });

  it("detects a rename", () => {
    const before = deriveDynamicPanels([makeAgent({ taskId: "t1", displayName: "Agent 1" })], []);
    const after = deriveDynamicPanels([makeAgent({ taskId: "t1", displayName: "Renamed" })], []);
    expect(panelRegistriesEqual(before, after)).toBe(false);
  });

  it("detects an added panel", () => {
    const before = deriveDynamicPanels([makeAgent({ taskId: "t1" })], []);
    const after = deriveDynamicPanels([makeAgent({ taskId: "t1" }), makeAgent({ taskId: "t2" })], []);
    expect(panelRegistriesEqual(before, after)).toBe(false);
  });
});

describe("activePanelComponentInSubSectionAtom", () => {
  it("resolves the active panel's component and is stable per id", () => {
    const filesComponent: ComponentType = () => null;
    registerPanelComponent("files", filesComponent);

    const store = createStore();
    store.set(panelRegistryAtom, buildStaticPanelDefinitions());
    store.set(activeWorkspaceIdAtom, "ws-join");
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      placement: { files: "left" },
      order: { left: ["files"] },
      activePanel: { left: "files" },
      expanded: { left: true },
    });

    const resolved = store.get(activePanelComponentInSubSectionAtom("left"));
    expect(resolved).toBe(filesComponent);
    expect(store.get(activePanelComponentInSubSectionAtom("left"))).toBe(resolved);
  });
});

describe("resolvedActivePanelIdInSubSectionAtom", () => {
  const PLUGIN_PANEL_ID = "plugin:linear-issue:issues";
  const pluginComponent: ComponentType = () => null;
  const pluginDefinitions = buildPluginPanelDefinitions([
    { id: PLUGIN_PANEL_ID, displayName: "Issues", icon: Puzzle, component: pluginComponent },
  ]);

  // A layout whose persisted active panel in "left" is the plugin panel, with "files"
  // also open — the state left behind when a plugin unloads (or has not loaded yet)
  // while its panel is the active tab.
  const seedStore = (workspaceId: string): ReturnType<typeof createStore> => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, workspaceId);
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      placement: { [PLUGIN_PANEL_ID]: "left", files: "left" },
      order: { left: [PLUGIN_PANEL_ID, "files"] },
      activePanel: { left: PLUGIN_PANEL_ID },
      expanded: { left: true },
    });
    return store;
  };

  it("falls back to the first open registered panel when the active id is unregistered", () => {
    const filesComponent: ComponentType = () => null;
    registerPanelComponent("files", filesComponent);
    const store = seedStore("ws-unregistered-active");
    // Static panels only: the plugin panel named by the layout has no definition.
    store.set(panelRegistryAtom, buildStaticPanelDefinitions());

    expect(store.get(resolvedActivePanelIdInSubSectionAtom("left"))).toBe("files");
    // The body renders the same resolved id the header highlights.
    expect(store.get(activePanelComponentInSubSectionAtom("left"))).toBe(filesComponent);
  });

  it("resolves to undefined when no open panel is registered", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-none-registered");
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      placement: { [PLUGIN_PANEL_ID]: "left" },
      order: { left: [PLUGIN_PANEL_ID] },
      activePanel: { left: PLUGIN_PANEL_ID },
      expanded: { left: true },
    });
    store.set(panelRegistryAtom, buildStaticPanelDefinitions());

    expect(store.get(resolvedActivePanelIdInSubSectionAtom("left"))).toBeUndefined();
    expect(store.get(activePanelComponentInSubSectionAtom("left"))).toBeUndefined();
  });

  it("self-heals back to the persisted active id when its definition (re)registers", () => {
    registerPanelComponent("files", () => null);
    const store = seedStore("ws-self-heal");
    store.set(panelRegistryAtom, buildStaticPanelDefinitions());
    expect(store.get(resolvedActivePanelIdInSubSectionAtom("left"))).toBe("files");

    // The plugin (re)loads: its definitions join the registry and — because the
    // fallback never pruned the layout — the persisted active id wins again.
    store.set(panelRegistryAtom, [...buildStaticPanelDefinitions(), ...pluginDefinitions]);
    expect(store.get(resolvedActivePanelIdInSubSectionAtom("left"))).toBe(PLUGIN_PANEL_ID);
    expect(store.get(activePanelComponentInSubSectionAtom("left"))).toBe(pluginComponent);
    expect(store.get(workspaceLayoutAtom).activePanel.left).toBe(PLUGIN_PANEL_ID);
  });
});
