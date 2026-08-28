import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceBranchInfo } from "~/api";
import { workspaceBranchAtomFamily } from "~/common/state/atoms/workspaceBranch.ts";

import { BRANCH_LOAD_GRACE_MS, useWorkspaceRowBranch } from "./useWorkspaceRowBranch.ts";

type Store = ReturnType<typeof createStore>;

const createWrapper = (store: Store) => {
  return ({ children }: { children: ReactNode }): ReactElement => <Provider store={store}>{children}</Provider>;
};

const setBranch = (store: Store, workspaceId: string, currentBranch: string): void => {
  store.set(workspaceBranchAtomFamily(workspaceId), { currentBranch, workspaceId } as WorkspaceBranchInfo);
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("useWorkspaceRowBranch", () => {
  it("reports loading (no branch) while the current branch hasn't streamed in yet", () => {
    const store = createStore();
    const { result } = renderHook(() => useWorkspaceRowBranch("ws1", "main"), { wrapper: createWrapper(store) });

    expect(result.current).toEqual({ branch: null, isLoading: true });
  });

  it("shows the current branch and never the source branch once it arrives", () => {
    const store = createStore();
    setBranch(store, "ws1", "dev/feature");
    const { result } = renderHook(() => useWorkspaceRowBranch("ws1", "main"), { wrapper: createWrapper(store) });

    expect(result.current).toEqual({ branch: "dev/feature", isLoading: false });
  });

  it("swaps the skeleton for the real branch when it streams in later, skipping the source branch", () => {
    const store = createStore();
    const { result } = renderHook(() => useWorkspaceRowBranch("ws1", "main"), { wrapper: createWrapper(store) });

    expect(result.current.isLoading).toBe(true);

    act(() => setBranch(store, "ws1", "dev/feature"));

    expect(result.current).toEqual({ branch: "dev/feature", isLoading: false });
  });

  it("falls back to the source branch after the grace window so the skeleton can't be permanent", () => {
    const store = createStore();
    const { result } = renderHook(() => useWorkspaceRowBranch("ws1", "main"), { wrapper: createWrapper(store) });

    expect(result.current).toEqual({ branch: null, isLoading: true });

    act(() => {
      vi.advanceTimersByTime(BRANCH_LOAD_GRACE_MS);
    });

    expect(result.current).toEqual({ branch: "main", isLoading: false });
  });

  it("shows nothing (no skeleton) after the grace window when there is no source branch either", () => {
    const store = createStore();
    const { result } = renderHook(() => useWorkspaceRowBranch("ws1", null), { wrapper: createWrapper(store) });

    act(() => {
      vi.advanceTimersByTime(BRANCH_LOAD_GRACE_MS);
    });

    expect(result.current).toEqual({ branch: null, isLoading: false });
  });
});
