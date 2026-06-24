import { Button, Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import type { RecentWorkspaceResponse, Workspace, WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, listRecentWorkspaces } from "~/api";
import { updateWorkspacesAtom } from "~/common/state/atoms/workspaces";

import { ClosedWorkspacesPill } from "./ClosedWorkspacesPill";
import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE } from "./popoverFriendlyModal";

// Unlike the fetch-coalescing test file, this one uses the REAL
// DeleteConfirmationDialog so we can exercise the dialog/popover
// interaction end-to-end. The row mock exposes a delete button that
// invokes the `onDelete` prop — sufficient to trigger the dialog.
vi.mock("./ClosedWorkspaceRow.tsx", () => ({
  ClosedWorkspaceRow: ({
    workspace,
    onReopen,
    onDelete,
  }: {
    workspace: RecentWorkspaceResponse;
    onReopen: (workspaceId: string) => void;
    onDelete: (workspace: RecentWorkspaceResponse) => void;
  }): ReactElement => (
    <div data-testid={`row-${workspace.objectId}`}>
      <span>{workspace.description}</span>
      <Button data-testid={`reopen-${workspace.objectId}`} onClick={() => onReopen(workspace.objectId)}>
        Reopen
      </Button>
      <Button
        data-testid={`delete-${workspace.objectId}`}
        onClick={(e) => {
          e.stopPropagation();
          onDelete(workspace);
        }}
      >
        Delete
      </Button>
    </div>
  ),
}));

vi.mock("~/common/NavigateUtils.ts", () => ({
  useImbueNavigate: (): Record<string, ReturnType<typeof vi.fn>> => ({
    navigateToWorkspace: vi.fn(),
    navigateToAgent: vi.fn(),
    navigateToAddWorkspace: vi.fn(),
    navigateToHome: vi.fn(),
    navigateToGlobalSettings: vi.fn(),
    navigateToRoot: vi.fn(),
  }),
}));

vi.mock("~/common/state/hooks/useOptimisticWorkspaceDelete.ts", () => ({
  useOptimisticWorkspaceDelete: (): { execute: ReturnType<typeof vi.fn> } => ({ execute: vi.fn() }),
}));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return {
    ...actual,
    listRecentWorkspaces: vi.fn(),
  };
});

type ListResponse = Awaited<ReturnType<typeof listRecentWorkspaces>>;

const mockWorkspace = (overrides: Partial<Workspace> & Pick<Workspace, "objectId">): Workspace =>
  ({
    projectId: "proj-1",
    organizationReference: "org-1",
    description: overrides.objectId,
    initializationStrategy: "CLONE" as WorkspaceInitializationStrategy,
    isOpen: false,
    isDeleted: false,
    ...overrides,
  }) as Workspace;

const mockRecent = (id: string): RecentWorkspaceResponse =>
  ({
    objectId: id,
    projectId: "proj-1",
    description: id,
    initializationStrategy: "CLONE" as WorkspaceInitializationStrategy,
    sourceBranch: null,
    isDeleted: false,
    createdAt: "",
    projectName: "proj-1",
    agentCount: 0,
    isOpen: false,
    lastActivityAt: "",
  }) as RecentWorkspaceResponse;

const okResponse = (ids: ReadonlyArray<string>): ListResponse =>
  ({ data: { workspaces: ids.map(mockRecent) } }) as ListResponse;

const flushPromises = async (): Promise<void> => {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
};

const seedStore = (closedIds: ReadonlyArray<string>): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(
    updateWorkspacesAtom,
    closedIds.map((id) => mockWorkspace({ objectId: id, isOpen: false })),
  );
  return store;
};

const renderPill = (store: ReturnType<typeof createStore>): ReturnType<typeof render> => {
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
  return render(<ClosedWorkspacesPill />, { wrapper: Wrapper });
};

const openPopover = async (): Promise<void> => {
  const trigger = screen.getByTestId(ElementIds.CLOSED_WORKSPACES_PILL);
  await act(async () => {
    fireEvent.click(trigger);
  });
  await flushPromises();
};

const clickDeleteOnRow = async (id: string): Promise<void> => {
  const deleteButton = screen.getByTestId(`delete-${id}`);
  await act(async () => {
    fireEvent.click(deleteButton);
  });
  await flushPromises();
};

const mockListRecent = vi.mocked(listRecentWorkspaces);

describe("ClosedWorkspacesPill — popover persistence across delete flow", () => {
  beforeEach(() => {
    mockListRecent.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("opens the confirmation dialog while keeping the popover content mounted", async () => {
    const store = seedStore(["ws-1", "ws-2"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2"]));

    renderPill(store);
    await openPopover();
    await clickDeleteOnRow("ws-1");

    expect(screen.getByTestId(ElementIds.DELETE_CONFIRMATION_DIALOG)).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).not.toBeNull();
  });

  it("marks the dialog content so popovers can recognize it as a friendly modal", async () => {
    const store = seedStore(["ws-1"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1"]));

    renderPill(store);
    await openPopover();
    await clickDeleteOnRow("ws-1");

    const dialog = screen.getByTestId(ElementIds.DELETE_CONFIRMATION_DIALOG);
    expect(dialog.getAttribute(POPOVER_FRIENDLY_MODAL_ATTRIBUTE)).toBe("true");
  });

  it("keeps the popover open after the user confirms a delete and removes the row from the list", async () => {
    const store = seedStore(["ws-1", "ws-2"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2"]));

    renderPill(store);
    await openPopover();
    await clickDeleteOnRow("ws-1");

    await act(async () => {
      fireEvent.click(screen.getByTestId(ElementIds.DELETE_CONFIRMATION_CONFIRM));
    });
    await flushPromises();

    expect(screen.queryByTestId(ElementIds.DELETE_CONFIRMATION_DIALOG)).toBeNull();
    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).not.toBeNull();
    expect(screen.queryByTestId("row-ws-1")).toBeNull();
    expect(screen.getByTestId("row-ws-2")).toBeTruthy();
  });

  it("keeps the popover open after the user cancels a delete, leaving rows untouched", async () => {
    const store = seedStore(["ws-1", "ws-2"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2"]));

    renderPill(store);
    await openPopover();
    await clickDeleteOnRow("ws-1");

    await act(async () => {
      fireEvent.click(screen.getByTestId(ElementIds.DELETE_CONFIRMATION_CANCEL));
    });
    await flushPromises();

    expect(screen.queryByTestId(ElementIds.DELETE_CONFIRMATION_DIALOG)).toBeNull();
    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).not.toBeNull();
    expect(screen.getByTestId("row-ws-1")).toBeTruthy();
    expect(screen.getByTestId("row-ws-2")).toBeTruthy();
  });

  it("supports successive deletes without the user needing to re-open the popover", async () => {
    // The core user value: a session of consecutive trash clicks stays in
    // the same expanded context — no toggle-back-and-forth.
    const store = seedStore(["ws-1", "ws-2", "ws-3"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2", "ws-3"]));

    renderPill(store);
    await openPopover();

    await clickDeleteOnRow("ws-1");
    await act(async () => {
      fireEvent.click(screen.getByTestId(ElementIds.DELETE_CONFIRMATION_CONFIRM));
    });
    await flushPromises();
    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).not.toBeNull();
    expect(screen.queryByTestId("row-ws-1")).toBeNull();

    await clickDeleteOnRow("ws-2");
    await act(async () => {
      fireEvent.click(screen.getByTestId(ElementIds.DELETE_CONFIRMATION_CONFIRM));
    });
    await flushPromises();
    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).not.toBeNull();
    expect(screen.queryByTestId("row-ws-2")).toBeNull();
    expect(screen.getByTestId("row-ws-3")).toBeTruthy();
  });

  it("still closes the popover when the user clicks Reopen on a row (existing dismiss-on-navigate)", async () => {
    const store = seedStore(["ws-1"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1"]));

    renderPill(store);
    await openPopover();
    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).not.toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByTestId("reopen-ws-1"));
    });
    await flushPromises();

    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).toBeNull();
  });

  it("still closes the popover when the user clicks Open all (existing dismiss-on-navigate)", async () => {
    const store = seedStore(["ws-1", "ws-2"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2"]));

    renderPill(store);
    await openPopover();

    await act(async () => {
      fireEvent.click(screen.getByTestId(ElementIds.CLOSED_WORKSPACES_OPEN_ALL_BUTTON));
    });
    await flushPromises();

    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).toBeNull();
  });

  it("unmounts the pill (and its popover) once the last closed workspace is gone — natural end of flow", async () => {
    const store = seedStore(["ws-1"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1"]));

    renderPill(store);
    expect(screen.getByTestId(ElementIds.CLOSED_WORKSPACES_PILL)).toBeTruthy();
    await openPopover();

    // Simulate the workspace flipping to deleted — the pill should unmount
    // on its own once closedWorkspaceIdsAtom returns empty.
    await act(async () => {
      store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isDeleted: true })]);
    });
    await flushPromises();

    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_PILL)).toBeNull();
    expect(screen.queryByTestId(ElementIds.CLOSED_WORKSPACES_DROPDOWN)).toBeNull();
  });
});
