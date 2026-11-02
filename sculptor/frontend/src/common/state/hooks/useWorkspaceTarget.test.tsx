import { cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { Workspace } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";

import { useWorkspaceTarget } from "./useWorkspaceTarget.ts";

type Store = ReturnType<typeof createStore>;

const createWrapper = (store: Store) => {
  return ({ children }: { children: ReactNode }): ReactElement => <Provider store={store}>{children}</Provider>;
};

const storeWith = (targetBranch: string | null): Store => {
  const store = createStore();
  const workspace: Workspace = {
    objectId: "ws1",
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "My workspace",
    initializationStrategy: WorkspaceInitializationStrategy.WORKTREE,
    targetBranch,
  };
  store.set(workspaceAtomFamily("ws1"), workspace);
  return store;
};

afterEach(() => {
  cleanup();
});

describe("useWorkspaceTarget", () => {
  it("is the workspace's own target", () => {
    const { result } = renderHook(() => useWorkspaceTarget("ws1"), {
      wrapper: createWrapper(storeWith("origin/release")),
    });

    expect(result.current).toBe("origin/release");
  });

  it("falls back to origin/main when the workspace has none", () => {
    const { result } = renderHook(() => useWorkspaceTarget("ws1"), { wrapper: createWrapper(storeWith(null)) });

    expect(result.current).toBe("origin/main");
  });
});
