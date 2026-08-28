import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RecentWorkspaceResponse, Workspace } from "~/api";
import { ElementIds } from "~/api";
import {
  optimisticDeleteWorkspaceAtom,
  rollbackDeleteWorkspaceAtom,
  updateWorkspacesAtom,
} from "~/common/state/atoms/workspaces.ts";

import { WorkspaceRow } from "./WorkspaceRow.tsx";

// The row composes heavy neighbors that are irrelevant to the deleting state;
// stub them so this test pins only the row's own affordance behavior.
vi.mock("~/pages/workspace/components/PrButton.tsx", () => ({
  PrButton: (): null => null,
}));
vi.mock("~/common/state/hooks/useGitProvider.ts", () => ({
  useGitProvider: (): null => null,
}));

type Store = ReturnType<typeof createStore>;

const createWrapper = (store: Store) => {
  return ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
};

const WORKSPACE_ID = "ws-row-1";

const recentRow = (): RecentWorkspaceResponse =>
  ({
    objectId: WORKSPACE_ID,
    projectId: "proj-1",
    description: "My workspace",
    sourceBranch: "main",
    isDeleted: false,
    isOpen: true,
    projectName: "repo",
    agentCount: 0,
    lastActivityAt: "2024-01-01T00:00:00.000Z",
    createdAt: "2024-01-01T00:00:00.000Z",
    initializationStrategy: "CLONE",
  }) as unknown as RecentWorkspaceResponse;

const liveWorkspace = (): Workspace =>
  ({
    objectId: WORKSPACE_ID,
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "My workspace",
    initializationStrategy: "CLONE",
    isOpen: true,
    isDeleted: false,
  }) as Workspace;

const renderRow = (store: Store): { onClick: ReturnType<typeof vi.fn>; onDelete: ReturnType<typeof vi.fn> } => {
  const onClick = vi.fn();
  const onDelete = vi.fn();
  render(
    <WorkspaceRow
      workspace={recentRow()}
      isFocused={false}
      onClick={onClick}
      onOpenInNewTab={vi.fn()}
      onDelete={onDelete}
    />,
    { wrapper: createWrapper(store) },
  );
  return { onClick, onDelete };
};

afterEach(() => {
  cleanup();
});

describe("WorkspaceRow deleting state", () => {
  it("renders a live row as interactive, with its delete affordance", () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [liveWorkspace()]);
    const { onClick } = renderRow(store);

    expect(screen.queryByText("Deleting…")).toBeNull();
    expect(screen.getByTestId(ElementIds.WORKSPACE_ROW_CONTEXT_MENU_DELETE)).toBeTruthy();

    fireEvent.click(screen.getByTestId(ElementIds.WORKSPACE_ROW));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders a tombstoned row dimmed, labeled Deleting…, and non-interactive", () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [liveWorkspace()]);
    store.set(optimisticDeleteWorkspaceAtom, WORKSPACE_ID);
    const { onClick } = renderRow(store);

    const row = screen.getByTestId(ElementIds.WORKSPACE_ROW);
    expect(screen.getByText("Deleting…")).toBeTruthy();
    expect(row.getAttribute("aria-disabled")).toBe("true");
    // The delete affordance is replaced by the pending label — no double-delete.
    expect(screen.queryByTestId(ElementIds.WORKSPACE_ROW_CONTEXT_MENU_DELETE)).toBeNull();

    fireEvent.click(row);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("un-dims live again when the store restores the workspace (failed delete rollback)", () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [liveWorkspace()]);
    const context = store.set(optimisticDeleteWorkspaceAtom, WORKSPACE_ID);

    renderRow(store);
    expect(screen.getByText("Deleting…")).toBeTruthy();

    act(() => {
      store.set(rollbackDeleteWorkspaceAtom, { workspaceId: WORKSPACE_ID, context });
    });

    expect(screen.queryByText("Deleting…")).toBeNull();
    expect(screen.getByTestId(ElementIds.WORKSPACE_ROW_CONTEXT_MENU_DELETE)).toBeTruthy();
  });
});
