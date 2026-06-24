import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import type { RecentWorkspaceResponse, Workspace, WorkspaceInitializationStrategy } from "~/api";
import { ElementIds, listRecentWorkspaces } from "~/api";
import { updateWorkspacesAtom } from "~/common/state/atoms/workspaces";

import { ClosedWorkspacesPill } from "./ClosedWorkspacesPill";

// The real ClosedWorkspaceRow pulls in tasks/git/PrButton — orthogonal to the
// fetch-coalescing logic under test. Replace with a minimal probe.
vi.mock("./ClosedWorkspaceRow.tsx", () => ({
  ClosedWorkspaceRow: ({ workspace }: { workspace: RecentWorkspaceResponse }): ReactElement => (
    <div data-testid={`row-${workspace.objectId}`}>{workspace.description}</div>
  ),
}));

vi.mock("./DeleteConfirmationDialog.tsx", () => ({
  DeleteConfirmationDialog: (): null => null,
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

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

const defer = <T,>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
};

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

const setClosedIds = (store: ReturnType<typeof createStore>, ids: ReadonlyArray<string>): void => {
  store.set(
    updateWorkspacesAtom,
    ids.map((id) => mockWorkspace({ objectId: id, isOpen: false })),
  );
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

const mockListRecent = vi.mocked(listRecentWorkspaces);

describe("ClosedWorkspacesPill — fetch coalescing (SCU-487)", () => {
  beforeEach(() => {
    mockListRecent.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not fetch while the popover is closed", () => {
    const store = seedStore(["ws-1", "ws-2"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2"]));

    renderPill(store);

    expect(mockListRecent).not.toHaveBeenCalled();
  });

  it("fetches once when the popover opens and renders the returned rows", async () => {
    const store = seedStore(["ws-1", "ws-2"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2"]));

    renderPill(store);
    await openPopover();

    expect(mockListRecent).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("row-ws-1")).toBeTruthy();
    expect(screen.getByTestId("row-ws-2")).toBeTruthy();
  });

  it("re-fetches when the closed-id set changes while the popover is open, keeping rows mounted", async () => {
    // The original bug: closedWorkspaceIdsAtom flipped synchronously (pill said
    // "Closed 3"), but the dropdown still showed the pre-change list (or 0
    // rows if the GET landed before the close-PATCH committed).
    const store = seedStore(["ws-1", "ws-2"]);
    const initial = defer<ListResponse>();
    const refetch = defer<ListResponse>();
    mockListRecent.mockReturnValueOnce(initial.promise as ReturnType<typeof listRecentWorkspaces>);
    mockListRecent.mockReturnValueOnce(refetch.promise as ReturnType<typeof listRecentWorkspaces>);

    renderPill(store);
    await openPopover();

    await act(async () => {
      initial.resolve(okResponse(["ws-1", "ws-2"]));
    });
    await flushPromises();
    expect(screen.getByTestId("row-ws-1")).toBeTruthy();
    expect(screen.getByTestId("row-ws-2")).toBeTruthy();

    // Add a third closed workspace — closedWorkspaceIdsAtom changes, effect fires.
    await act(async () => {
      setClosedIds(store, ["ws-1", "ws-2", "ws-3"]);
    });
    await flushPromises();

    expect(mockListRecent).toHaveBeenCalledTimes(2);
    // Rows from the previous response remain in the DOM during the in-flight
    // refetch — we don't unmount the list and swap to a Spinner. This is
    // what fixed the Playwright "click detached node" flake.
    expect(screen.getByTestId("row-ws-1")).toBeTruthy();
    expect(screen.getByTestId("row-ws-2")).toBeTruthy();

    await act(async () => {
      refetch.resolve(okResponse(["ws-1", "ws-2", "ws-3"]));
    });
    await flushPromises();
    expect(screen.getByTestId("row-ws-3")).toBeTruthy();
  });

  it("coalesces a burst of closed-id changes into at most two sequential fetches", async () => {
    // The in-flight gate (isFetchingRef) suppresses concurrent triggers; the
    // lastFetchedKey reactivity catches the latest snapshot up afterwards.
    // Net effect: N triggers in one in-flight window → 1 follow-up, not N.
    const store = seedStore(["ws-1"]);
    const initial = defer<ListResponse>();
    const catchup = defer<ListResponse>();
    mockListRecent.mockReturnValueOnce(initial.promise as ReturnType<typeof listRecentWorkspaces>);
    mockListRecent.mockReturnValueOnce(catchup.promise as ReturnType<typeof listRecentWorkspaces>);

    renderPill(store);
    await openPopover();
    expect(mockListRecent).toHaveBeenCalledTimes(1);

    // Three updates while the first fetch is still in flight.
    await act(async () => {
      setClosedIds(store, ["ws-1", "ws-2"]);
    });
    await act(async () => {
      setClosedIds(store, ["ws-1", "ws-2", "ws-3"]);
    });
    await act(async () => {
      setClosedIds(store, ["ws-1", "ws-2", "ws-3", "ws-4"]);
    });

    // None of those triggered a parallel fetch — gated by isFetchingRef.
    expect(mockListRecent).toHaveBeenCalledTimes(1);

    // Resolve initial fetch (with its now-stale snapshot).
    await act(async () => {
      initial.resolve(okResponse(["ws-1"]));
    });
    await flushPromises();

    // Exactly one follow-up — the three intermediate triggers coalesced.
    expect(mockListRecent).toHaveBeenCalledTimes(2);

    // Resolve the catch-up; nothing further fires.
    await act(async () => {
      catchup.resolve(okResponse(["ws-1", "ws-2", "ws-3", "ws-4"]));
    });
    await flushPromises();
    expect(mockListRecent).toHaveBeenCalledTimes(2);
  });

  it("does not refetch when re-opening the popover with an unchanged closed-id set", async () => {
    // lastFetchedKey caches the last-seen snapshot across popover open/close
    // cycles. Re-open with the same set should be a no-op.
    const store = seedStore(["ws-1"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1"]));

    renderPill(store);
    await openPopover(); // open  → fetch
    expect(mockListRecent).toHaveBeenCalledTimes(1);

    await openPopover(); // close → no fetch
    await openPopover(); // open  → still no fetch (key unchanged)

    expect(mockListRecent).toHaveBeenCalledTimes(1);
  });

  it("resolves the spinner even under React.StrictMode (cancelledRef reset on remount)", async () => {
    // React 18 StrictMode dev simulates an extra mount → unmount → remount
    // cycle for every component. The cleanup of the cancelledRef effect runs
    // during the simulated unmount and the same ref is reused on the
    // simulated remount (refs survive strict-mode simulation). Without an
    // explicit reset in the effect setup, cancelledRef.current stays `true`
    // and every subsequent fetch returns early — the dropdown's spinner
    // never resolves. This test wraps the pill in <StrictMode> to lock the
    // reset in.
    const store = seedStore(["ws-1", "ws-2"]);
    mockListRecent.mockResolvedValue(okResponse(["ws-1", "ws-2"]));

    render(<ClosedWorkspacesPill />, {
      wrapper: ({ children }: { children: ReactNode }): ReactElement => (
        <StrictMode>
          <Provider store={store}>
            <Theme>{children}</Theme>
          </Provider>
        </StrictMode>
      ),
    });
    await openPopover();

    // Rows would not appear (and the spinner would stay) if cancelledRef
    // were stuck at true after StrictMode's simulated unmount.
    expect(screen.getByTestId("row-ws-1")).toBeTruthy();
    expect(screen.getByTestId("row-ws-2")).toBeTruthy();
  });

  it("ignores a fetch that resolves after the component unmounts (cancelledRef)", async () => {
    const store = seedStore(["ws-1"]);
    const inFlight = defer<ListResponse>();
    mockListRecent.mockReturnValueOnce(inFlight.promise as ReturnType<typeof listRecentWorkspaces>);

    const { unmount } = renderPill(store);
    await openPopover();
    expect(mockListRecent).toHaveBeenCalledTimes(1);

    unmount();

    // Resolving after unmount must not throw, must not warn, must not write
    // to a torn-down tree. cancelledRef short-circuits the post-await body.
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    await act(async () => {
      inFlight.resolve(okResponse(["ws-1"]));
    });
    await flushPromises();
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
