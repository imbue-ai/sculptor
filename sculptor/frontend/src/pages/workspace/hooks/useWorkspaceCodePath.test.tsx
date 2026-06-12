import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Workspace } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces";

import { useWorkspaceCodePath } from "./useWorkspaceCodePath";

vi.mock("~/common/NavigateUtils.ts", () => ({
  useWorkspacePageParams: (): { workspaceID: string } => ({ workspaceID: "ws-from-url" }),
}));

const ENVIRONMENT_ID = "/Users/test/.sculptor/workspaces/abc123";

const makeWorkspace = (overrides: Partial<Workspace> = {}): Workspace => ({
  objectId: "ws-1",
  projectId: "proj-1",
  organizationReference: "org-1",
  description: "test",
  initializationStrategy: WorkspaceInitializationStrategy.CLONE,
  environmentId: ENVIRONMENT_ID,
  ...overrides,
});

const renderWithStore = (
  store: ReturnType<typeof createStore>,
  workspaceId?: string,
): { result: { current: string | null } } => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  return renderHook(() => useWorkspaceCodePath(workspaceId), { wrapper });
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("useWorkspaceCodePath", () => {
  it("returns `${environmentId}/code` for CLONE workspaces", () => {
    const store = createStore();
    store.set(
      workspaceAtomFamily("ws-1"),
      makeWorkspace({ initializationStrategy: WorkspaceInitializationStrategy.CLONE }),
    );

    const { result } = renderWithStore(store, "ws-1");

    expect(result.current).toBe(`${ENVIRONMENT_ID}/code`);
  });

  it("returns `${environmentId}/code` for WORKTREE workspaces", () => {
    // Regression: previously, WORKTREE workspaces fell through to repoInfo.repoPath
    // (the user's source repo) — so every absolute path inside the worktree was
    // flagged as "outside the workspace" by makeRelative().
    const store = createStore();
    store.set(
      workspaceAtomFamily("ws-1"),
      makeWorkspace({ initializationStrategy: WorkspaceInitializationStrategy.WORKTREE }),
    );

    const { result } = renderWithStore(store, "ws-1");

    expect(result.current).toBe(`${ENVIRONMENT_ID}/code`);
  });

  it("returns null when a CLONE workspace has no environmentId yet", () => {
    const store = createStore();
    store.set(
      workspaceAtomFamily("ws-1"),
      makeWorkspace({
        initializationStrategy: WorkspaceInitializationStrategy.CLONE,
        environmentId: null,
      }),
    );

    const { result } = renderWithStore(store, "ws-1");

    expect(result.current).toBeNull();
  });

  it("returns null when a WORKTREE workspace has no environmentId yet", () => {
    const store = createStore();
    store.set(
      workspaceAtomFamily("ws-1"),
      makeWorkspace({
        initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
        environmentId: null,
      }),
    );

    const { result } = renderWithStore(store, "ws-1");

    expect(result.current).toBeNull();
  });

  it("returns null when the workspace is not loaded", () => {
    const store = createStore();
    // Don't populate the workspace atom.

    const { result } = renderWithStore(store, "ws-missing");

    expect(result.current).toBeNull();
  });
});
