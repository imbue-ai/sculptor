import { getDefaultStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { taskAtomFamily, taskIdsAtom } from "../../../common/state/atoms/tasks.ts";
import { workspaceAtomFamily, workspaceIdsAtom } from "../../../common/state/atoms/workspaces.ts";
import { panelRegistryAtom } from "../../panels/atoms.ts";
import type { PanelDefinition } from "../../panels/types.ts";
import { buildAgentProvider } from "../dynamic/agentCommands.ts";
import { buildPanelTogglesProvider } from "../dynamic/panels.ts";
import { buildWorkspaceProvider } from "../dynamic/workspaceCommands.tsx";
import type { CommandRuntime } from "../runtime.ts";
import type { PaletteContext } from "../types.ts";

const ROOT_CTX: PaletteContext = {
  route: { isHome: true, isWorkspace: false, isSettings: false, isAddWorkspace: false, isAgent: false },
  activeWorkspaceId: null,
  activeAgentId: null,
  hasChatPanel: false,
  hasTerminalPanel: false,
  isZenMode: false,
  page: null,
};

const PAGE_WS_CTX: PaletteContext = { ...ROOT_CTX, page: "workspaces.switch" };

const makeRuntime = (): CommandRuntime => {
  const noop = (): void => {};
  return {
    store: getDefaultStore(),
    navigate: {
      toHome: noop,
      toSettings: noop,
      toAddWorkspace: noop,
      toWorkspace: vi.fn(),
      toAgent: vi.fn(),
    },
    ui: {
      toggleHelpDialog: noop,
      toggleDevPanel: noop,
      toggleZenMode: noop,
      toggleFocusMode: noop,
      toggleMaximizePanel: noop,
      toggleLeftPanel: noop,
      toggleBottomPanel: noop,
      toggleRightPanel: noop,
      togglePanel: noop,
      setTheme: noop,
      focusChatInput: noop,
      showChatSearch: noop,
      jumpChatToBottom: noop,
      nextWorkspaceTab: noop,
      previousWorkspaceTab: noop,
      nextAgent: noop,
      previousAgent: noop,
      createAgent: noop,
      openReportProblem: noop,
      clearActiveTerminal: noop,
    },
    config: { updateField: vi.fn().mockResolvedValue(undefined) },
    electron: { isAvailable: false, reloadWindow: noop },
  };
};

const seedWorkspace = (id: string, description: string): void => {
  const store = getDefaultStore();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  store.set(workspaceAtomFamily(id), { objectId: id, description, isOpen: true } as any);
};

const setWorkspaceIds = (ids: Array<string>): void => {
  getDefaultStore().set(workspaceIdsAtom, ids);
};

const setTasks = (
  tasks: Array<{ id: string; title?: string; workspaceId: string; createdAt: string; initialPrompt?: string }>,
): void => {
  // tasksArrayAtom is derived from taskIdsAtom + taskAtomFamily, so we
  // seed those primitive atoms instead of trying to write the derived one.
  const store = getDefaultStore();
  for (const t of tasks) {
    store.set(
      taskAtomFamily(t.id),

      {
        id: t.id,
        title: t.title ?? null,
        workspaceId: t.workspaceId,
        createdAt: t.createdAt,
        initialPrompt: t.initialPrompt ?? "",
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any,
    );
  }
  store.set(
    taskIdsAtom,
    tasks.map((t) => t.id),
  );
};

beforeEach(() => {
  setWorkspaceIds([]);
  setTasks([]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildWorkspaceProvider", () => {
  it("emits no commands when there are zero workspaces", () => {
    const provider = buildWorkspaceProvider(makeRuntime());
    expect(provider.produce(ROOT_CTX)).toHaveLength(0);
  });

  it("emits the page-opener even with one workspace (with singular subtitle)", () => {
    seedWorkspace("ws1", "Solo");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceProvider(makeRuntime()).produce(ROOT_CTX);
    // Page-opener stays visible regardless of workspace count — every
    // other palette command stays visible+disabled rather than vanishing
    // when it doesn't apply, and Cmd+P always landing on the same row
    // is the consistent shape.
    const opener = cmds.find((c) => c.id === "workspaces.switch");
    expect(opener?.pageId).toBe("workspaces.switch");
    expect(opener?.subtitle).toBe("1 workspace");
    expect(cmds.find((c) => c.id === "workspaces.page.ws1")).toBeDefined();
  });

  it("emits the page-opener with 2+ workspaces (with plural subtitle)", () => {
    seedWorkspace("ws1", "First");
    seedWorkspace("ws2", "Second");
    setWorkspaceIds(["ws1", "ws2"]);
    const cmds = buildWorkspaceProvider(makeRuntime()).produce(ROOT_CTX);
    const opener = cmds.find((c) => c.id === "workspaces.switch");
    expect(opener?.pageId).toBe("workspaces.switch");
    expect(opener?.subtitle).toContain("2 workspaces");
  });

  it("labels the current workspace's page-scoped entry as 'Current workspace'", () => {
    seedWorkspace("ws1", "Active");
    seedWorkspace("ws2", "Other");
    setWorkspaceIds(["ws1", "ws2"]);
    const provider = buildWorkspaceProvider(makeRuntime());
    const ctx: PaletteContext = { ...ROOT_CTX, activeWorkspaceId: "ws1" };
    const cmds = provider.produce(ctx);
    expect(cmds.find((c) => c.id === "workspaces.page.ws1")?.subtitle).toBe("Current workspace");
    expect(cmds.find((c) => c.id === "workspaces.page.ws2")?.subtitle).toBeUndefined();
  });

  it("page-scoped entries are scoped to the workspaces.switch sub-page", () => {
    seedWorkspace("ws1", "Foo");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceProvider(makeRuntime()).produce(PAGE_WS_CTX);
    const pageCmd = cmds.find((c) => c.id === "workspaces.page.ws1");
    expect(pageCmd?.onPage).toBe("workspaces.switch");
    expect(pageCmd?.title).toBe("Foo");
  });

  it("perform navigates to the workspace", () => {
    const runtime = makeRuntime();
    seedWorkspace("ws1", "X");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceProvider(runtime).produce(ROOT_CTX);
    const cmd = cmds.find((c) => c.id === "workspaces.page.ws1")!;
    cmd.perform({ ctx: ROOT_CTX, keepOpen: false, pushPage: vi.fn() });
    expect(runtime.navigate.toWorkspace).toHaveBeenCalledWith("ws1");
  });

  it("treats blank descriptions as 'Untitled'", () => {
    seedWorkspace("ws1", "   ");
    setWorkspaceIds(["ws1"]);
    const cmd = buildWorkspaceProvider(makeRuntime())
      .produce(PAGE_WS_CTX)
      .find((c) => c.id === "workspaces.page.ws1");
    expect(cmd?.title).toBe("Untitled");
  });

  it("does NOT emit any `workspaces.go.*` ids (top-level cleanup regression-lock)", () => {
    seedWorkspace("ws1", "First");
    seedWorkspace("ws2", "Second");
    setWorkspaceIds(["ws1", "ws2"]);
    const cmds = buildWorkspaceProvider(makeRuntime()).produce(ROOT_CTX);
    expect(cmds.find((c) => c.id.startsWith("workspaces.go."))).toBeUndefined();
  });
});

describe("buildAgentProvider", () => {
  // The agent switcher is intentionally scoped to the workspace the user
  // is currently viewing. When `ctx.activeWorkspaceId` is null (e.g.
  // Home / Settings) it emits nothing.
  const WS1_CTX: PaletteContext = {
    ...ROOT_CTX,
    activeWorkspaceId: "ws1",
    route: { ...ROOT_CTX.route, isWorkspace: true },
  };

  it("emits a disabled 'Switch agent...' entry when there are no tasks", () => {
    const cmds = buildAgentProvider(makeRuntime()).produce(WS1_CTX);
    const opener = cmds.find((c) => c.id === "agents.switch");
    expect(opener).toBeDefined();
    expect(opener?.disabled).toBe(true);
    // No per-agent rows when there's nothing to switch to.
    expect(cmds.filter((c) => c.id.startsWith("agents.page."))).toHaveLength(0);
  });

  it("emits no commands when there is no active workspace", () => {
    setTasks([
      { id: "t1", title: "A", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "B", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
    ]);
    const cmds = buildAgentProvider(makeRuntime()).produce(ROOT_CTX);
    expect(cmds).toHaveLength(0);
  });

  it("emits a disabled 'Switch agent...' entry (and no agent rows) when only one agent exists", () => {
    setTasks([{ id: "t1", title: "Lone task", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" }]);
    const cmds = buildAgentProvider(makeRuntime()).produce(WS1_CTX);
    const opener = cmds.find((c) => c.id === "agents.switch");
    expect(opener).toBeDefined();
    expect(opener?.disabled).toBe(true);
    expect(cmds.filter((c) => c.id.startsWith("agents.page."))).toHaveLength(0);
  });

  it("'Switch agent...' is enabled (not disabled) when 2+ agents exist", () => {
    setTasks([
      { id: "t1", title: "A", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "B", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
    ]);
    const cmds = buildAgentProvider(makeRuntime()).produce(WS1_CTX);
    const opener = cmds.find((c) => c.id === "agents.switch")!;
    expect(opener.disabled).toBeFalsy();
  });

  it("emits the page-opener + agent rows with 2+ agents in the current workspace", () => {
    setTasks([
      { id: "t1", title: "A", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "B", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
    ]);
    const cmds = buildAgentProvider(makeRuntime()).produce(WS1_CTX);
    expect(cmds.find((c) => c.id === "agents.switch")?.pageId).toBe("agents.switch");
    expect(cmds.find((c) => c.id === "agents.page.t1")).toBeDefined();
    expect(cmds.find((c) => c.id === "agents.page.t2")).toBeDefined();
  });

  it("excludes agents that belong to other workspaces", () => {
    setTasks([
      { id: "t1", title: "Mine 1", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "Mine 2", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
      { id: "t3", title: "Other workspace", workspaceId: "ws2", createdAt: "2024-01-03T00:00:00Z" },
    ]);
    const cmds = buildAgentProvider(makeRuntime()).produce(WS1_CTX);
    expect(cmds.find((c) => c.id === "agents.page.t3")).toBeUndefined();
  });

  it("labels the current agent on its page-scoped entry", () => {
    setTasks([
      { id: "t1", title: "A", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "B", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
    ]);
    const ctx: PaletteContext = { ...WS1_CTX, activeAgentId: "t1" };
    const cmds = buildAgentProvider(makeRuntime()).produce(ctx);
    expect(cmds.find((c) => c.id === "agents.page.t1")?.subtitle).toBe("Current agent");
  });

  it("falls back to the initial prompt when no title is set", () => {
    setTasks([
      {
        id: "t1",
        workspaceId: "ws1",
        createdAt: "2024-01-01T00:00:00Z",
        initialPrompt: "Refactor the renderer",
      },
      {
        id: "t2",
        title: "Other",
        workspaceId: "ws1",
        createdAt: "2024-01-02T00:00:00Z",
      },
    ]);
    const cmd = buildAgentProvider(makeRuntime())
      .produce(WS1_CTX)
      .find((c) => c.id === "agents.page.t1");
    expect(cmd?.title).toContain("Refactor the renderer");
  });

  it("page-scoped entries declare onPage = agents.switch", () => {
    setTasks([
      { id: "t1", title: "A", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "B", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
    ]);
    const cmd = buildAgentProvider(makeRuntime())
      .produce({ ...WS1_CTX, page: "agents.switch" })
      .find((c) => c.id === "agents.page.t1");
    expect(cmd?.onPage).toBe("agents.switch");
  });

  it("perform navigates to the current workspace + agent ids", () => {
    const runtime = makeRuntime();
    setTasks([
      { id: "t1", title: "A", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "B", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
    ]);
    const cmd = buildAgentProvider(runtime)
      .produce(WS1_CTX)
      .find((c) => c.id === "agents.page.t1")!;
    cmd.perform({ ctx: WS1_CTX, keepOpen: false, pushPage: vi.fn() });
    expect(runtime.navigate.toAgent).toHaveBeenCalledWith("ws1", "t1");
  });

  it("does NOT emit any `agents.go.*` ids (top-level cleanup regression-lock)", () => {
    setTasks([
      { id: "t1", title: "A", workspaceId: "ws1", createdAt: "2024-01-01T00:00:00Z" },
      { id: "t2", title: "B", workspaceId: "ws1", createdAt: "2024-01-02T00:00:00Z" },
    ]);
    const cmds = buildAgentProvider(makeRuntime()).produce(WS1_CTX);
    expect(cmds.find((c) => c.id.startsWith("agents.go."))).toBeUndefined();
  });
});

describe("buildPanelTogglesProvider", () => {
  const WORKSPACE_CTX: PaletteContext = {
    ...ROOT_CTX,
    route: { ...ROOT_CTX.route, isHome: false, isWorkspace: true },
  };

  // Stand-in icon — the panel registry stores LucideIcon-shaped components
  // and the provider reads `panel.icon` straight onto the Command. Any
  // function-shaped component works for these unit tests; we just need
  // the field to round-trip. Cast through `unknown` so we don't depend
  // on lucide-react's full forwardRef shape.
  const TestIcon = (): null => null;

  const seedRegistry = (panels: Array<Pick<PanelDefinition, "id" | "displayName">>): void => {
    const full = panels.map(
      (p) =>
        ({
          id: p.id,
          displayName: p.displayName,
          icon: TestIcon as unknown,
          defaultZone: "top-left",
          defaultShortcut: "",
          component: (() => null) as unknown,
        }) as unknown as PanelDefinition,
    );
    getDefaultStore().set(panelRegistryAtom, full);
  };

  beforeEach(() => {
    getDefaultStore().set(panelRegistryAtom, []);
  });

  it("emits no commands off-workspace", () => {
    seedRegistry([
      { id: "files", displayName: "File browser" },
      { id: "terminal", displayName: "Terminal" },
    ]);
    const cmds = buildPanelTogglesProvider(makeRuntime()).produce(ROOT_CTX);
    expect(cmds).toHaveLength(0);
  });

  it("emits one command per registered panel on a workspace route", () => {
    seedRegistry([
      { id: "files", displayName: "File browser" },
      { id: "terminal", displayName: "Terminal" },
      { id: "actions", displayName: "Actions" },
      { id: "todo-list", displayName: "Agent tasks" },
    ]);
    const cmds = buildPanelTogglesProvider(makeRuntime()).produce(WORKSPACE_CTX);
    expect(cmds.map((c) => c.id).sort()).toEqual(
      [
        "view.toggle_panel.files",
        "view.toggle_panel.terminal",
        "view.toggle_panel.actions",
        "view.toggle_panel.todo-list",
      ].sort(),
    );
    expect(cmds.find((c) => c.id === "view.toggle_panel.files")?.title).toBe("Toggle File browser");
    expect(cmds.find((c) => c.id === "view.toggle_panel.todo-list")?.title).toBe("Toggle Agent tasks");
  });

  it("places every panel toggle in the View group and closes the palette after firing", () => {
    // We previously kept the palette open after a panel toggle so users
    // could flip several in a row; that made heavier panels (file
    // browser) feel laggy because the palette and the panel re-rendered
    // concurrently. Closing first lets the panel mount alone.
    seedRegistry([{ id: "files", displayName: "File browser" }]);
    const cmd = buildPanelTogglesProvider(makeRuntime()).produce(WORKSPACE_CTX)[0]!;
    expect(cmd.group).toBe("view");
    expect(cmd.keepOpen).not.toBe(true);
  });

  it("scopes every panel toggle to the view.panels sub-page", () => {
    seedRegistry([
      { id: "files", displayName: "File browser" },
      { id: "terminal", displayName: "Terminal" },
    ]);
    const cmds = buildPanelTogglesProvider(makeRuntime()).produce(WORKSPACE_CTX);
    for (const cmd of cmds) {
      expect(cmd.onPage).toBe("view.panels");
    }
  });

  it("attaches a search boost so panel toggles outrank settings rows that share their name", () => {
    // See dynamic/panels.ts for the rationale: without the boost,
    // \"Settings: Actions\" (page-scoped exact title match) outranks
    // \"Toggle Actions\" (page-scoped word-prefix). The boost reverses
    // that. Magnitude is checked, not the exact value, so a future
    // tuning of the constant doesn't break this test.
    seedRegistry([{ id: "actions", displayName: "Actions" }]);
    const cmd = buildPanelTogglesProvider(makeRuntime()).produce(WORKSPACE_CTX)[0]!;
    expect(cmd.boost).toBeGreaterThan(5);
  });

  it('the file-browser panel matches by display name AND short-name aliases ("files", "explorer")', () => {
    // The display name "File browser" already covers searches for
    // "file browser" and "browser" via the title; the alias keywords add
    // the legacy short name "files" and the VS Code shorthand "explorer".
    seedRegistry([{ id: "files", displayName: "File browser" }]);
    const cmd = buildPanelTogglesProvider(makeRuntime()).produce(WORKSPACE_CTX)[0]!;
    expect(cmd.title.toLowerCase()).toContain("file browser");
    const keywords = (cmd.keywords ?? []).map((k) => k.toLowerCase());
    expect(keywords).toContain("files");
    expect(keywords).toContain("explorer");
  });

  it('does NOT use the word "plugin" in any user-visible string on a panel toggle', () => {
    seedRegistry([
      { id: "files", displayName: "File browser" },
      { id: "terminal", displayName: "Terminal" },
    ]);
    const cmds = buildPanelTogglesProvider(makeRuntime()).produce(WORKSPACE_CTX);
    for (const cmd of cmds) {
      expect(cmd.title.toLowerCase()).not.toContain("plugin");
      expect((cmd.subtitle ?? "").toLowerCase()).not.toContain("plugin");
      for (const k of cmd.keywords ?? []) {
        expect(k.toLowerCase()).not.toContain("plugin");
      }
    }
  });

  it("perform calls runtime.ui.togglePanel with the panel id", () => {
    seedRegistry([{ id: "terminal", displayName: "Terminal" }]);
    const runtime = makeRuntime();
    runtime.ui.togglePanel = vi.fn();
    const cmd = buildPanelTogglesProvider(runtime).produce(WORKSPACE_CTX)[0]!;
    cmd.perform({ ctx: WORKSPACE_CTX, keepOpen: true, pushPage: vi.fn() });
    expect(runtime.ui.togglePanel).toHaveBeenCalledWith("terminal");
  });

  it("picks up panels added to the registry without re-creating the provider", () => {
    // Future-panel scenario: a workspace with the Notes feature flag on
    // appends `notesPanelDefinition` to the registry mid-session. The
    // provider reads `panelRegistryAtom` at produce time, so the new
    // panel appears in Cmd+K immediately without any palette wiring.
    seedRegistry([{ id: "files", displayName: "File browser" }]);
    const provider = buildPanelTogglesProvider(makeRuntime());
    expect(provider.produce(WORKSPACE_CTX).map((c) => c.id)).toEqual(["view.toggle_panel.files"]);
    seedRegistry([
      { id: "files", displayName: "File browser" },
      { id: "notes", displayName: "Notes" },
    ]);
    expect(
      provider
        .produce(WORKSPACE_CTX)
        .map((c) => c.id)
        .sort(),
    ).toEqual(["view.toggle_panel.files", "view.toggle_panel.notes"].sort());
  });
});
