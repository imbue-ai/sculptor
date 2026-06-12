import { describe, expect, it, vi } from "vitest";

import { buildAgentActions } from "../contextActions/agentActions.ts";
import type { Agent, AgentActionRuntime, WorkspaceAction, WorkspaceActionRuntime } from "../contextActions/types.ts";
import { buildWorkspaceActions } from "../contextActions/workspaceActions.ts";

const fakeWorkspace = (id: string): { objectId: string; description: string | null } =>
  ({ objectId: id, description: `ws-${id}` }) as never;

const fakeAgent = (id: string): Agent =>
  ({
    id,
    title: `agent-${id}`,
    workspaceId: "w1",
    initialPrompt: "",
    createdAt: "2026-04-01T00:00:00Z",
    updatedAt: "2026-04-01T00:00:00Z",
    lastReadAt: null,
    status: "running",
  }) as never;

type WorkspaceRuntimeOverrides = {
  canCloseOthers?: boolean;
  hasUncommittedChanges?: boolean;
  hasOpenPr?: boolean;
  canCreatePr?: boolean;
  prTerm?: "merge request" | "pull request";
  canOpenInOS?: boolean;
  isMacUi?: boolean;
};

const makeWorkspaceRuntime = (overrides: WorkspaceRuntimeOverrides = {}): WorkspaceActionRuntime => ({
  beginRename: vi.fn(),
  closeWorkspace: vi.fn(),
  closeOtherWorkspaces: vi.fn(),
  closeAllWorkspaces: vi.fn(),
  beginDelete: vi.fn(),
  canCloseOthers: vi.fn(() => overrides.canCloseOthers ?? true),
  commitChanges: vi.fn(),
  createMergeRequest: vi.fn(),
  openMergeRequest: vi.fn(),
  openInApp: vi.fn(),
  hasUncommittedChanges: vi.fn(() => overrides.hasUncommittedChanges ?? false),
  hasOpenPr: vi.fn(() => overrides.hasOpenPr ?? false),
  canCreatePr: vi.fn(() => overrides.canCreatePr ?? true),
  prTerm: vi.fn(() => overrides.prTerm ?? "pull request"),
  canOpenInOS: vi.fn(() => overrides.canOpenInOS ?? true),
  isMacUi: vi.fn(() => overrides.isMacUi ?? true),
});

const makeAgentRuntime = (): AgentActionRuntime => ({
  beginRename: vi.fn(),
  markUnread: vi.fn(),
  beginDelete: vi.fn(),
});

describe("buildWorkspaceActions", () => {
  it("emits the canonical right-click menu set in order", () => {
    const actions = buildWorkspaceActions(makeWorkspaceRuntime());
    expect(actions.map((a) => a.id)).toEqual([
      "commit",
      "create_pr",
      "open_pr",
      "rename",
      "close",
      "close_others",
      "close_all",
      "delete",
    ]);
  });

  it("close_others is hidden when there is only one tab open", () => {
    const actions = buildWorkspaceActions(makeWorkspaceRuntime({ canCloseOthers: false }));
    const closeOthers = actions.find((a) => a.id === "close_others") as WorkspaceAction;
    expect(closeOthers.visible?.(fakeWorkspace("w1") as never)).toBe(false);
  });

  it("delete is destructive and adds a separator", () => {
    const actions = buildWorkspaceActions(makeWorkspaceRuntime());
    const del = actions.find((a) => a.id === "delete") as WorkspaceAction;
    expect(del.destructive).toBe(true);
    expect(del.separatorBefore).toBe(true);
  });

  it("perform invokes the runtime with the workspace target", () => {
    const runtime = makeWorkspaceRuntime();
    const actions = buildWorkspaceActions(runtime);
    const ws = fakeWorkspace("w1");
    actions.find((a) => a.id === "rename")?.perform(ws as never);
    actions.find((a) => a.id === "close")?.perform(ws as never);
    actions.find((a) => a.id === "delete")?.perform(ws as never);
    expect(runtime.beginRename).toHaveBeenCalledWith(ws);
    expect(runtime.closeWorkspace).toHaveBeenCalledWith(ws);
    expect(runtime.beginDelete).toHaveBeenCalledWith(ws);
  });

  it("commit is disabled when there are no uncommitted changes, enabled otherwise", () => {
    const noChanges = buildWorkspaceActions(makeWorkspaceRuntime({ hasUncommittedChanges: false }));
    const withChanges = buildWorkspaceActions(makeWorkspaceRuntime({ hasUncommittedChanges: true }));
    const ws = fakeWorkspace("w1") as never;
    expect(noChanges.find((a) => a.id === "commit")?.disabled?.(ws)).toBe(true);
    expect(withChanges.find((a) => a.id === "commit")?.disabled?.(ws)).toBe(false);
  });

  it("commit perform routes to runtime.commitChanges", () => {
    const runtime = makeWorkspaceRuntime();
    const actions = buildWorkspaceActions(runtime);
    const ws = fakeWorkspace("w1");
    actions.find((a) => a.id === "commit")?.perform(ws as never);
    expect(runtime.commitChanges).toHaveBeenCalledWith(ws);
  });

  it("create_pr title flips to 'Create merge request' on GitLab", () => {
    const ws = fakeWorkspace("w1") as never;
    const gh = buildWorkspaceActions(makeWorkspaceRuntime({ prTerm: "pull request" }));
    const gl = buildWorkspaceActions(makeWorkspaceRuntime({ prTerm: "merge request" }));
    expect(gh.find((a) => a.id === "create_pr")?.getTitle?.(ws)).toBe("Create pull request");
    expect(gl.find((a) => a.id === "create_pr")?.getTitle?.(ws)).toBe("Create merge request");
  });

  it("create_pr is disabled when an open PR already exists", () => {
    const noPr = buildWorkspaceActions(makeWorkspaceRuntime({ canCreatePr: true }));
    const withOpenPr = buildWorkspaceActions(makeWorkspaceRuntime({ canCreatePr: false }));
    const ws = fakeWorkspace("w1") as never;
    expect(noPr.find((a) => a.id === "create_pr")?.disabled?.(ws)).toBe(false);
    expect(withOpenPr.find((a) => a.id === "create_pr")?.disabled?.(ws)).toBe(true);
  });

  it("open_pr is disabled when no open PR exists, enabled when one does", () => {
    const noPr = buildWorkspaceActions(makeWorkspaceRuntime({ hasOpenPr: false }));
    const openPr = buildWorkspaceActions(makeWorkspaceRuntime({ hasOpenPr: true }));
    const ws = fakeWorkspace("w1") as never;
    expect(noPr.find((a) => a.id === "open_pr")?.disabled?.(ws)).toBe(true);
    expect(openPr.find((a) => a.id === "open_pr")?.disabled?.(ws)).toBe(false);
  });

  it("open_pr title flips to 'Open merge request' on GitLab", () => {
    const ws = fakeWorkspace("w1") as never;
    const gh = buildWorkspaceActions(makeWorkspaceRuntime({ prTerm: "pull request" }));
    const gl = buildWorkspaceActions(makeWorkspaceRuntime({ prTerm: "merge request" }));
    expect(gh.find((a) => a.id === "open_pr")?.getTitle?.(ws)).toBe("Open pull request");
    expect(gl.find((a) => a.id === "open_pr")?.getTitle?.(ws)).toBe("Open merge request");
  });

  it("open_pr perform routes to runtime.openMergeRequest", () => {
    const runtime = makeWorkspaceRuntime({ hasOpenPr: true });
    const actions = buildWorkspaceActions(runtime);
    const ws = fakeWorkspace("w1");
    actions.find((a) => a.id === "open_pr")?.perform(ws as never);
    expect(runtime.openMergeRequest).toHaveBeenCalledWith(ws);
  });
});

describe("buildAgentActions", () => {
  it("emits the canonical right-click menu set", () => {
    const actions = buildAgentActions(makeAgentRuntime());
    expect(actions.map((a) => a.id)).toEqual(["rename", "mark_unread", "delete"]);
  });

  it("delete is destructive and routes through the runtime", () => {
    const runtime = makeAgentRuntime();
    const actions = buildAgentActions(runtime);
    const agent = fakeAgent("a1");
    actions.find((a) => a.id === "delete")?.perform(agent);
    expect(runtime.beginDelete).toHaveBeenCalledWith(agent);
  });

  it("mark_unread fires the runtime hook", () => {
    const runtime = makeAgentRuntime();
    const actions = buildAgentActions(runtime);
    const agent = fakeAgent("a2");
    actions.find((a) => a.id === "mark_unread")?.perform(agent);
    expect(runtime.markUnread).toHaveBeenCalledWith(agent);
  });
});
