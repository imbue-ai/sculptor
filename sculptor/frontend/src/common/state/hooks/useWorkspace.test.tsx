import { act, renderHook } from "@testing-library/react";
import type { WritableAtom } from "jotai";
import { Provider, useAtomValue, useSetAtom } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import type { Workspace } from "../../../api";
import { WorkspaceInitializationStrategy } from "../../../api";
import { updateWorkspacesAtom, workspaceAtomFamily, workspaceIdsAtom, workspacesArrayAtom } from "../atoms/workspaces";
import { useIsWorkspaceDeleted, useWorkspace } from "./useWorkspace";

const createMockWorkspace = (overrides: Partial<Workspace> = {}): Workspace => ({
  objectId: "ws_test123",
  createdAt: "2024-01-01T00:00:00Z",
  updatedAt: "2024-01-01T00:00:00Z",
  projectId: "proj_test123",
  organizationReference: "org_test",
  description: "Test workspace",
  initializationStrategy: WorkspaceInitializationStrategy.IN_PLACE,
  sourceBranch: "main",
  sourceGitHash: null,
  isDeleted: false,
  ...overrides,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/array-type
type AnyWritableAtom = WritableAtom<unknown, any[], any>;
type AtomInitialValues = Array<readonly [AnyWritableAtom, unknown]>;

// Helper component to hydrate atoms with initial values
const HydrateAtoms = ({
  initialValues,
  children,
}: {
  initialValues: AtomInitialValues;
  children: ReactNode;
}): ReactNode => {
  useHydrateAtoms(initialValues);
  return children;
};

// Wrapper for hooks that provides jotai Provider with initial values
const createWrapper = (initialValues: AtomInitialValues = []) => {
  return ({ children }: { children: ReactNode }): ReactNode => (
    <Provider>
      <HydrateAtoms initialValues={initialValues}>{children}</HydrateAtoms>
    </Provider>
  );
};

describe("useWorkspace", () => {
  it("returns null when workspaceId is null", () => {
    const { result } = renderHook(() => useWorkspace(null), {
      wrapper: createWrapper(),
    });
    expect(result.current).toBeNull();
  });

  it("returns null when workspaceId is undefined", () => {
    const { result } = renderHook(() => useWorkspace(undefined), {
      wrapper: createWrapper(),
    });
    expect(result.current).toBeNull();
  });

  it("returns null when workspace is not loaded", () => {
    const { result } = renderHook(() => useWorkspace("ws_unknown"), {
      wrapper: createWrapper(),
    });
    expect(result.current).toBeNull();
  });

  it("returns workspace data when loaded", () => {
    const workspace = createMockWorkspace({ objectId: "ws_loaded" });

    const { result } = renderHook(() => useWorkspace("ws_loaded"), {
      wrapper: createWrapper([[workspaceAtomFamily("ws_loaded"), workspace]]),
    });

    expect(result.current).toEqual(workspace);
    expect(result.current?.initializationStrategy).toBe(WorkspaceInitializationStrategy.IN_PLACE);
  });

  it("returns workspace with CLONE strategy", () => {
    const workspace = createMockWorkspace({
      objectId: "ws_clone",
      initializationStrategy: WorkspaceInitializationStrategy.CLONE,
    });

    const { result } = renderHook(() => useWorkspace("ws_clone"), {
      wrapper: createWrapper([[workspaceAtomFamily("ws_clone"), workspace]]),
    });

    expect(result.current?.initializationStrategy).toBe(WorkspaceInitializationStrategy.CLONE);
  });
});

describe("updateWorkspacesAtom", () => {
  it("updates workspace atoms when streaming provides new data", () => {
    const wrapper = createWrapper();

    const { result } = renderHook(
      () => {
        const updateWorkspaces = useSetAtom(updateWorkspacesAtom);
        const workspace = useWorkspace("ws_streamed");
        return { updateWorkspaces, workspace };
      },
      { wrapper },
    );

    expect(result.current.workspace).toBeNull();

    // Simulate streaming update
    const newWorkspace = createMockWorkspace({ objectId: "ws_streamed" });
    act(() => {
      result.current.updateWorkspaces([newWorkspace]);
    });

    expect(result.current.workspace).toEqual(newWorkspace);
  });

  it("updates multiple workspaces at once", () => {
    const wrapper = createWrapper();

    const { result } = renderHook(
      () => {
        const updateWorkspaces = useSetAtom(updateWorkspacesAtom);
        const workspaces = useAtomValue(workspacesArrayAtom) ?? [];
        return { updateWorkspaces, workspaces };
      },
      { wrapper },
    );

    expect(result.current.workspaces).toHaveLength(0);

    // Simulate streaming update with multiple workspaces
    const workspace1 = createMockWorkspace({ objectId: "ws_1" });
    const workspace2 = createMockWorkspace({ objectId: "ws_2" });
    act(() => {
      result.current.updateWorkspaces([workspace1, workspace2]);
    });

    expect(result.current.workspaces).toHaveLength(2);
  });

  it("drops stream-deleted workspaces from the id membership that drives pulled-list refreshes", () => {
    const wrapper = createWrapper();

    const { result } = renderHook(
      () => {
        const updateWorkspaces = useSetAtom(updateWorkspacesAtom);
        const workspaceIds = useAtomValue(workspaceIdsAtom);
        const workspaces = useAtomValue(workspacesArrayAtom) ?? [];
        return { updateWorkspaces, workspaceIds, workspaces };
      },
      { wrapper },
    );

    // Create two workspaces via stream
    const workspace1 = createMockWorkspace({ objectId: "ws_1" });
    const workspace2 = createMockWorkspace({ objectId: "ws_2" });
    act(() => {
      result.current.updateWorkspaces([workspace1, workspace2]);
    });

    expect(result.current.workspaces).toHaveLength(2);

    // Simulate a stream update marking ws_1 as deleted
    const deletedWorkspace = createMockWorkspace({ objectId: "ws_1", isDeleted: true });
    act(() => {
      result.current.updateWorkspaces([deletedWorkspace]);
    });

    expect(result.current.workspaces).toHaveLength(1);
    expect(result.current.workspaces[0].objectId).toBe("ws_2");

    // ws_1 leaves the id membership — components with their own pulled lists
    // (e.g. RecentWorkspaces) key their refetch on this, and the refreshed
    // server response no longer contains the deleted workspace.
    expect(result.current.workspaceIds).toEqual(["ws_2"]);
  });
});

describe("useIsWorkspaceDeleted", () => {
  it("returns false when workspaceId is null", () => {
    const { result } = renderHook(() => useIsWorkspaceDeleted(null), {
      wrapper: createWrapper([[workspaceIdsAtom, []]]),
    });
    expect(result.current).toBe(false);
  });

  it("returns false before workspaces have loaded", () => {
    // Default workspaceIdsAtom is undefined — workspaces not yet streamed
    const { result } = renderHook(() => useIsWorkspaceDeleted("ws_123"), {
      wrapper: createWrapper(),
    });
    expect(result.current).toBe(false);
  });

  it("returns true when workspaces have loaded but workspace is missing", () => {
    const { result } = renderHook(() => useIsWorkspaceDeleted("ws_gone"), {
      wrapper: createWrapper([[workspaceIdsAtom, []]]),
    });
    expect(result.current).toBe(true);
  });

  it("returns false when workspace exists", () => {
    const workspace = createMockWorkspace({ objectId: "ws_exists" });
    const { result } = renderHook(() => useIsWorkspaceDeleted("ws_exists"), {
      wrapper: createWrapper([
        [workspaceIdsAtom, ["ws_exists"]],
        [workspaceAtomFamily("ws_exists"), workspace],
      ]),
    });
    expect(result.current).toBe(false);
  });
});
