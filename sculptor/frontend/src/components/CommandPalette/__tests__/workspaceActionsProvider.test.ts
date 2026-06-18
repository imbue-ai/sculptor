import { getDefaultStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExternalApp } from "../../../api";
import { workspaceAtomFamily, workspaceIdsAtom } from "../../../common/state/atoms/workspaces.ts";
import type { WorkspaceActionRuntime } from "../contextActions/types.ts";
import type { CommandRuntime } from "../runtime.ts";
import type { PaletteContext } from "../types.ts";

// Mock the open-in items so the provider's Open-in branch isn't gated on
// the test runner's platform. `getOpenWithItems()` normally returns
// macOS-only items via `isMac()`.
vi.mock("../../../common/openInApp/items.tsx", () => {
  const StubIcon = (): null => null;
  return {
    getOpenWithItems: (): Array<{
      app: ExternalApp;
      label: string;
      icon: string;
      IconComponent: typeof StubIcon;
    }> => [
      { app: "finder", label: "Finder", icon: "finder.png", IconComponent: StubIcon },
      { app: "vscode", label: "VS Code", icon: "vscode.png", IconComponent: StubIcon },
    ],
    getPreferredApp: (): ExternalApp | null => "vscode",
  };
});

import { buildWorkspaceActionsProvider } from "../dynamic/workspaceActions.ts";

const ROOT_CTX: PaletteContext = {
  route: { isHome: true, isWorkspace: false, isSettings: false, isAgent: false },
  activeWorkspaceId: null,
  activeAgentId: null,
  hasChatPanel: false,
  hasTerminalPanel: false,
  isZenMode: false,
  page: null,
};

const wsCtx = (id: string): PaletteContext => ({
  ...ROOT_CTX,
  activeWorkspaceId: id,
  route: { ...ROOT_CTX.route, isHome: false, isWorkspace: true },
});

const seedWorkspace = (id: string, description: string): void => {
  const store = getDefaultStore();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  store.set(workspaceAtomFamily(id), { objectId: id, description, isOpen: true } as any);
};

const setWorkspaceIds = (ids: Array<string>): void => {
  getDefaultStore().set(workspaceIdsAtom, ids);
};

const makeCommandRuntime = (): CommandRuntime => {
  const noop = (): void => {};
  return {
    store: getDefaultStore(),
    navigate: { toHome: noop, toSettings: noop, toWorkspace: vi.fn(), toAgent: vi.fn() },
    modal: { openNewWorkspaceFromPalette: noop },
    ui: {
      toggleHelpDialog: noop,
      toggleDevPanel: noop,
      toggleZenMode: noop,
      toggleFocusMode: noop,
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

type ActionRuntimeOverrides = {
  hasUncommittedChanges?: boolean;
  hasOpenPr?: boolean;
  canCreatePr?: boolean;
  prTerm?: "merge request" | "pull request";
  canOpenInOS?: boolean;
};

const makeActionRuntime = (overrides: ActionRuntimeOverrides = {}): WorkspaceActionRuntime => ({
  beginRename: vi.fn(),
  closeWorkspace: vi.fn(),
  closeOtherWorkspaces: vi.fn(),
  closeAllWorkspaces: vi.fn(),
  beginDelete: vi.fn(),
  canCloseOthers: vi.fn(() => true),
  commitChanges: vi.fn(),
  createMergeRequest: vi.fn(),
  openMergeRequest: vi.fn(),
  openInApp: vi.fn(),
  hasUncommittedChanges: vi.fn(() => overrides.hasUncommittedChanges ?? false),
  hasOpenPr: vi.fn(() => overrides.hasOpenPr ?? false),
  canCreatePr: vi.fn(() => overrides.canCreatePr ?? true),
  prTerm: vi.fn(() => overrides.prTerm ?? "pull request"),
  canOpenInOS: vi.fn(() => overrides.canOpenInOS ?? true),
  isMacUi: vi.fn(() => true),
});

beforeEach(() => {
  setWorkspaceIds([]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildWorkspaceActionsProvider", () => {
  it("emits no commands when there is no active workspace", () => {
    const provider = buildWorkspaceActionsProvider(makeCommandRuntime(), makeActionRuntime());
    expect(provider.produce(ROOT_CTX)).toHaveLength(0);
  });

  it("emits the page opener + sub-page action entries for the active workspace", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceActionsProvider(makeCommandRuntime(), makeActionRuntime()).produce(wsCtx("ws1"));
    expect(cmds.find((c) => c.id === "workspaces.actions.open")).toBeDefined();
    expect(cmds.find((c) => c.id === "workspaces.action.ws1.commit")).toBeDefined();
    expect(cmds.find((c) => c.id === "workspaces.action.ws1.create_pr")).toBeDefined();
    expect(cmds.find((c) => c.id === "workspaces.action.ws1.open_pr")).toBeDefined();
  });

  it("commit command is disabled when there are no uncommitted changes", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const noChanges = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ hasUncommittedChanges: false }),
    ).produce(wsCtx("ws1"));
    const withChanges = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ hasUncommittedChanges: true }),
    ).produce(wsCtx("ws1"));
    expect(noChanges.find((c) => c.id === "workspaces.action.ws1.commit")?.disabled).toBe(true);
    expect(withChanges.find((c) => c.id === "workspaces.action.ws1.commit")?.disabled).toBe(false);
  });

  it("open_pr command is disabled when no open PR exists", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceActionsProvider(makeCommandRuntime(), makeActionRuntime({ hasOpenPr: false })).produce(
      wsCtx("ws1"),
    );
    expect(cmds.find((c) => c.id === "workspaces.action.ws1.open_pr")?.disabled).toBe(true);
  });

  it("create_pr title flips for GitLab repos", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const gh = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ prTerm: "pull request" }),
    ).produce(wsCtx("ws1"));
    const gl = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ prTerm: "merge request" }),
    ).produce(wsCtx("ws1"));
    expect(gh.find((c) => c.id === "workspaces.action.ws1.create_pr")?.title).toBe("Create pull request");
    expect(gl.find((c) => c.id === "workspaces.action.ws1.create_pr")?.title).toBe("Create merge request");
  });

  it("create_pr subtitle flips for GitLab repos", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const gh = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ prTerm: "pull request" }),
    ).produce(wsCtx("ws1"));
    const gl = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ prTerm: "merge request" }),
    ).produce(wsCtx("ws1"));
    expect(gh.find((c) => c.id === "workspaces.action.ws1.create_pr")?.subtitle).toBe(
      "Push and open a new pull request",
    );
    expect(gl.find((c) => c.id === "workspaces.action.ws1.create_pr")?.subtitle).toBe(
      "Push and open a new merge request",
    );
  });

  it("open_pr subtitle flips for GitLab repos", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const gh = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ hasOpenPr: true, prTerm: "pull request" }),
    ).produce(wsCtx("ws1"));
    const gl = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ hasOpenPr: true, prTerm: "merge request" }),
    ).produce(wsCtx("ws1"));
    expect(gh.find((c) => c.id === "workspaces.action.ws1.open_pr")?.subtitle).toBe(
      "Open the existing pull request in your browser",
    );
    expect(gl.find((c) => c.id === "workspaces.action.ws1.open_pr")?.subtitle).toBe(
      "Open the existing merge request in your browser",
    );
  });

  it("create_pr keywords are provider-aware (GitHub-only on GitHub, GitLab-only on GitLab)", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const gh = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ prTerm: "pull request" }),
    ).produce(wsCtx("ws1"));
    const gl = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ prTerm: "merge request" }),
    ).produce(wsCtx("ws1"));
    const ghKw = gh.find((c) => c.id === "workspaces.action.ws1.create_pr")?.keywords ?? [];
    const glKw = gl.find((c) => c.id === "workspaces.action.ws1.create_pr")?.keywords ?? [];
    expect(ghKw).toContain("pr");
    expect(ghKw).toContain("pull");
    expect(ghKw).toContain("github");
    expect(ghKw).not.toContain("mr");
    expect(ghKw).not.toContain("merge");
    expect(ghKw).not.toContain("gitlab");
    expect(glKw).toContain("mr");
    expect(glKw).toContain("merge");
    expect(glKw).toContain("gitlab");
    expect(glKw).not.toContain("pr");
    expect(glKw).not.toContain("pull");
    expect(glKw).not.toContain("github");
    // "request" stays on both — generic noun some users prefer.
    expect(ghKw).toContain("request");
    expect(glKw).toContain("request");
  });

  it("emits an Open-in opener and one entry per app from getOpenWithItems()", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceActionsProvider(makeCommandRuntime(), makeActionRuntime()).produce(wsCtx("ws1"));
    const opener = cmds.find((c) => c.id === "workspaces.open_in.open.ws1");
    expect(opener).toBeDefined();
    expect(opener?.pageId).toBe("workspace.open_in");
    expect(opener?.onPage).toBe("workspace.actions");
    expect(cmds.find((c) => c.id === "workspaces.open_in.ws1.finder")?.title).toBe("Open in Finder");
    expect(cmds.find((c) => c.id === "workspaces.open_in.ws1.vscode")?.title).toBe("Open in VS Code");
  });

  it("Open-in entries are disabled when the backend cannot open paths", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceActionsProvider(makeCommandRuntime(), makeActionRuntime({ canOpenInOS: false })).produce(
      wsCtx("ws1"),
    );
    expect(cmds.find((c) => c.id === "workspaces.open_in.open.ws1")?.disabled).toBe(true);
    expect(cmds.find((c) => c.id === "workspaces.open_in.ws1.finder")?.disabled).toBe(true);
    expect(cmds.find((c) => c.id === "workspaces.open_in.ws1.vscode")?.disabled).toBe(true);
  });

  it("commit row surfaces the disabled reason in the subtitle (no hover needed)", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ hasUncommittedChanges: false }),
    ).produce(wsCtx("ws1"));
    const commit = cmds.find((c) => c.id === "workspaces.action.ws1.commit");
    expect(commit?.subtitle).toBe("No uncommitted changes");
  });

  it("commit row shows the static subtitle when enabled", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ hasUncommittedChanges: true }),
    ).produce(wsCtx("ws1"));
    expect(cmds.find((c) => c.id === "workspaces.action.ws1.commit")?.subtitle).toBe(
      "Stage and commit current changes",
    );
  });

  it("create_pr disabled subtitle uses the git provider's term", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const gh = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ canCreatePr: false, prTerm: "pull request" }),
    ).produce(wsCtx("ws1"));
    const gl = buildWorkspaceActionsProvider(
      makeCommandRuntime(),
      makeActionRuntime({ canCreatePr: false, prTerm: "merge request" }),
    ).produce(wsCtx("ws1"));
    expect(gh.find((c) => c.id === "workspaces.action.ws1.create_pr")?.subtitle).toBe(
      "An open pull request already exists",
    );
    expect(gl.find((c) => c.id === "workspaces.action.ws1.create_pr")?.subtitle).toBe(
      "An open merge request already exists",
    );
  });

  it("Open-in entries carry a disabledReason when canOpenInOS is false", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const cmds = buildWorkspaceActionsProvider(makeCommandRuntime(), makeActionRuntime({ canOpenInOS: false })).produce(
      wsCtx("ws1"),
    );
    expect(cmds.find((c) => c.id === "workspaces.open_in.open.ws1")?.disabledReason).toContain(
      "Opening external apps is unavailable",
    );
    expect(cmds.find((c) => c.id === "workspaces.open_in.ws1.finder")?.disabledReason).toContain(
      "Opening external apps is unavailable",
    );
  });

  it("perform on a per-app Open-in command routes to runtime.openInApp(target, app)", () => {
    seedWorkspace("ws1", "Active");
    setWorkspaceIds(["ws1"]);
    const actionRuntime = makeActionRuntime();
    const cmds = buildWorkspaceActionsProvider(makeCommandRuntime(), actionRuntime).produce(wsCtx("ws1"));
    const finderCmd = cmds.find((c) => c.id === "workspaces.open_in.ws1.finder")!;
    finderCmd.perform({ ctx: wsCtx("ws1"), keepOpen: false, pushPage: vi.fn() });
    expect(actionRuntime.openInApp).toHaveBeenCalledWith(expect.objectContaining({ objectId: "ws1" }), "finder");
  });
});
