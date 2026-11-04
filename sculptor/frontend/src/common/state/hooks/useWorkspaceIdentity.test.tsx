import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { GitBranchIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Workspace } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";
import { workspaceBranchAtomFamily } from "~/common/state/atoms/workspaceBranch.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";

import { IDENTITY_LABEL_GRACE_MS, useWorkspaceIdentityLabel } from "./useWorkspaceIdentity.ts";

type Store = ReturnType<typeof createStore>;

const createWrapper = (store: Store) => {
  return ({ children }: { children: ReactNode }): ReactElement => <Provider store={store}>{children}</Provider>;
};

const setLiveBranch = (store: Store, workspaceId: string, currentBranch: string): void => {
  store.set(workspaceBranchAtomFamily(workspaceId), { currentBranch, workspaceId });
};

const setWorkspace = (
  store: Store,
  workspaceId: string,
  branches: { sourceBranch: string | null; requestedBranchName: string | null },
): void => {
  const workspace: Workspace = {
    objectId: workspaceId,
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "My workspace",
    initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
    ...branches,
  };
  store.set(workspaceAtomFamily(workspaceId), workspace);
};

const passGraceWindow = (): void => {
  act(() => {
    vi.advanceTimersByTime(IDENTITY_LABEL_GRACE_MS);
  });
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("useWorkspaceIdentityLabel", () => {
  it("is loading while no current branch is known", () => {
    const store = createStore();
    setWorkspace(store, "ws1", { sourceBranch: "main", requestedBranchName: "dev/feature" });

    const { result } = renderHook(() => useWorkspaceIdentityLabel({ workspaceId: "ws1" }), {
      wrapper: createWrapper(store),
    });

    expect(result.current).toEqual({ status: "LOADING" });
  });

  it("labels the workspace with its live branch, copied as-is, under the branch icon", () => {
    const store = createStore();
    setLiveBranch(store, "ws1", "dev/feature");

    const { result } = renderHook(() => useWorkspaceIdentityLabel({ workspaceId: "ws1" }), {
      wrapper: createWrapper(store),
    });

    expect(result.current).toEqual({
      status: "READY",
      text: "dev/feature",
      copyText: "dev/feature",
      icon: GitBranchIcon,
    });
  });

  it("shows a fetched current branch at once, without waiting for the stream", () => {
    const store = createStore();

    const { result } = renderHook(() => useWorkspaceIdentityLabel({ workspaceId: "ws1", fetchedBranch: "dev/rest" }), {
      wrapper: createWrapper(store),
    });

    expect(result.current).toMatchObject({ status: "READY", text: "dev/rest" });
  });

  it("prefers the live branch over a fetched one", () => {
    const store = createStore();
    setLiveBranch(store, "ws1", "dev/renamed");

    const { result } = renderHook(() => useWorkspaceIdentityLabel({ workspaceId: "ws1", fetchedBranch: "dev/rest" }), {
      wrapper: createWrapper(store),
    });

    expect(result.current).toMatchObject({ status: "READY", text: "dev/renamed" });
  });

  it("swaps loading for the live branch when it streams in", () => {
    const store = createStore();
    setWorkspace(store, "ws1", { sourceBranch: "main", requestedBranchName: "dev/requested" });
    const { result } = renderHook(() => useWorkspaceIdentityLabel({ workspaceId: "ws1" }), {
      wrapper: createWrapper(store),
    });

    act(() => setLiveBranch(store, "ws1", "dev/feature"));

    expect(result.current).toMatchObject({ status: "READY", text: "dev/feature" });
  });

  it("falls back to the requested branch name once the grace window passes", () => {
    const store = createStore();
    setWorkspace(store, "ws1", { sourceBranch: "main", requestedBranchName: "dev/requested" });
    const { result } = renderHook(() => useWorkspaceIdentityLabel({ workspaceId: "ws1" }), {
      wrapper: createWrapper(store),
    });

    passGraceWindow();

    expect(result.current).toMatchObject({ status: "READY", text: "dev/requested", copyText: "dev/requested" });
  });

  it("never labels a workspace with the branch it was created from", () => {
    const store = createStore();
    setWorkspace(store, "ws1", { sourceBranch: "main", requestedBranchName: null });
    const { result } = renderHook(() => useWorkspaceIdentityLabel({ workspaceId: "ws1" }), {
      wrapper: createWrapper(store),
    });

    passGraceWindow();

    expect(result.current).toEqual({ status: "UNAVAILABLE" });
  });

  it("restarts the grace window when it is asked about another workspace", () => {
    const store = createStore();
    setWorkspace(store, "ws1", { sourceBranch: "main", requestedBranchName: "dev/one" });
    setWorkspace(store, "ws2", { sourceBranch: "main", requestedBranchName: "dev/two" });
    const { result, rerender } = renderHook(
      ({ workspaceId }: { workspaceId: string }) => useWorkspaceIdentityLabel({ workspaceId }),
      { wrapper: createWrapper(store), initialProps: { workspaceId: "ws1" } },
    );
    passGraceWindow();

    rerender({ workspaceId: "ws2" });

    expect(result.current).toEqual({ status: "LOADING" });
    passGraceWindow();
    expect(result.current).toMatchObject({ status: "READY", text: "dev/two" });
  });

  it("waits afresh on returning to a workspace whose grace window already ran out", () => {
    const store = createStore();
    setWorkspace(store, "ws1", { sourceBranch: "main", requestedBranchName: "dev/one" });
    setWorkspace(store, "ws2", { sourceBranch: "main", requestedBranchName: "dev/two" });
    const { result, rerender } = renderHook(
      ({ workspaceId }: { workspaceId: string }) => useWorkspaceIdentityLabel({ workspaceId }),
      { wrapper: createWrapper(store), initialProps: { workspaceId: "ws1" } },
    );
    passGraceWindow();
    rerender({ workspaceId: "ws2" });

    rerender({ workspaceId: "ws1" });

    expect(result.current).toEqual({ status: "LOADING" });
    passGraceWindow();
    expect(result.current).toMatchObject({ status: "READY", text: "dev/one" });
  });
});
