import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { Workspace } from "../../../api";
import { HTTPException } from "../../Errors.ts";
import { queryClient } from "../../queryClient.ts";
import { workspaceDeleteErrorToastAtom } from "../atoms/toasts";
import {
  asLiveWorkspace,
  isWorkspaceDeletingAtomFamily,
  Tombstone,
  updateWorkspacesAtom,
  workspaceAtomFamily,
} from "../atoms/workspaces";
import { MUTATION_SETTLE_TIMEOUT_MS } from "../mutations";
import { useOptimisticWorkspaceDelete } from "./useOptimisticWorkspaceDelete";

// Mock the delete endpoint so we can force failures and inspect retry targets.
const { mockDeleteWorkspace } = vi.hoisted(() => ({
  mockDeleteWorkspace: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    deleteWorkspace: mockDeleteWorkspace,
    // updateWorkspacesAtom hydration path may PATCH; keep it inert.
    updateWorkspace: vi.fn().mockResolvedValue({ data: {} }),
    batchUpdateOpenState: vi.fn().mockResolvedValue({ data: {} }),
  };
});

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const mockWorkspace = (objectId: string, overrides: Partial<Workspace> = {}): Workspace =>
  ({
    objectId,
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "",
    initializationStrategy: "CLONE",
    isOpen: true,
    isDeleted: false,
    ...overrides,
  }) as Workspace;

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const renderDeleteHook = (
  store: ReturnType<typeof createStore>,
): { execute: (workspaceId: string, workspaceName: string) => void } => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
    createElement(QueryClientProvider, { client: queryClient }, createElement(Provider, { store }, children));
  const { result } = renderHook(() => useOptimisticWorkspaceDelete({ onNavigateAfterDelete: vi.fn() }), { wrapper });
  return result.current;
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useOptimisticWorkspaceDelete", () => {
  it("bounds the delete request's settle time so a hung backend eventually reaches the failure path (SCU-1833)", async () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A")]);
    const { execute } = renderDeleteHook(store);

    mockDeleteWorkspace.mockResolvedValue(undefined);
    execute("ws-A", "Workspace A");
    await flushMicrotasks();

    expect(mockDeleteWorkspace).toHaveBeenCalledWith(
      expect.objectContaining({
        meta: expect.objectContaining({ skipWsAck: true, timeout: MUTATION_SETTLE_TIMEOUT_MS }),
      }),
    );
  });

  it("sends the DELETE even when the workspace is missing from the WS store (SCU-1832)", async () => {
    // A Home row can come from the REST list while the stream never delivered
    // the workspace (reconnecting / wedged backend). The store's ignorance
    // must not silently swallow the user's delete.
    const store = createStore();
    const { execute } = renderDeleteHook(store);

    mockDeleteWorkspace.mockResolvedValue(undefined);
    execute("ws-ghost", "Ghost Workspace");
    await flushMicrotasks();

    expect(mockDeleteWorkspace).toHaveBeenCalledOnce();
    expect(mockDeleteWorkspace).toHaveBeenCalledWith(expect.objectContaining({ path: { workspace_id: "ws-ghost" } }));
    expect(store.get(workspaceDeleteErrorToastAtom)).toBeNull();
  });

  it("treats a 404 as success: the workspace is already gone, so the tombstone stands (SCU-1832)", async () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A")]);
    const { execute } = renderDeleteHook(store);

    mockDeleteWorkspace.mockRejectedValue(new HTTPException(404, "Workspace ws-A not found"));
    execute("ws-A", "Workspace A");
    await flushMicrotasks();

    expect(store.get(workspaceDeleteErrorToastAtom)).toBeNull();
    expect(store.get(workspaceAtomFamily("ws-A"))).toBeInstanceOf(Tombstone);
  });

  it("restores everything on a failed delete — the workspace atom AND the deleting state (SCU-1834)", async () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A")]);
    const { execute } = renderDeleteHook(store);

    mockDeleteWorkspace.mockRejectedValue(new HTTPException(500, "database is locked"));
    execute("ws-A", "Workspace A");
    await flushMicrotasks();

    expect(store.get(workspaceDeleteErrorToastAtom)?.title).toContain("Failed to delete");
    expect(asLiveWorkspace(store.get(workspaceAtomFamily("ws-A")))).not.toBeNull();
    // The Home row derives its "Deleting…" state from the same store, so it
    // un-dims everywhere at once — no add-only overlay left behind.
    expect(store.get(isWorkspaceDeletingAtomFamily("ws-A"))).toBe(false);
  });

  it("keeps every view consistent when a frame arrives mid-delete: the workspace is back everywhere (SCU-1834)", async () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A")]);
    const { execute } = renderDeleteHook(store);

    mockDeleteWorkspace.mockReturnValue(new Promise(() => {}));
    execute("ws-A", "Workspace A");
    await flushMicrotasks();

    // Tombstoned: "Deleting…" on Home, gone from sidebar.
    expect(store.get(workspaceAtomFamily("ws-A"))).toBeInstanceOf(Tombstone);
    expect(store.get(isWorkspaceDeletingAtomFamily("ws-A"))).toBe(true);

    // An authoritative frame lands while the request is in flight.
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A")]);

    // Server truth wins in EVERY view: restored in the store and no longer
    // deleting on Home — one store, one answer.
    expect(asLiveWorkspace(store.get(workspaceAtomFamily("ws-A")))).not.toBeNull();
    expect(store.get(isWorkspaceDeletingAtomFamily("ws-A"))).toBe(false);
  });

  it("yields the rollback to an authoritative frame that landed mid-request (SCU-1834)", async () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A", { description: "stale" })]);
    const { execute } = renderDeleteHook(store);

    let rejectRequest: (e: Error) => void = () => {};
    mockDeleteWorkspace.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectRequest = reject;
      }),
    );
    execute("ws-A", "Workspace A");
    await flushMicrotasks();

    // A frame with fresher data lands while the DELETE is in flight.
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A", { description: "fresh" })]);

    rejectRequest(new HTTPException(500, "database is locked"));
    await flushMicrotasks();

    // The rollback must not clobber the frame with the stale mutate-time snapshot.
    expect(asLiveWorkspace(store.get(workspaceAtomFamily("ws-A")))?.description).toBe("fresh");
  });

  it("retries the workspace captured per-call, not the most recently failed workspace", async () => {
    // Regression for the shared-ref bug: the toast's Retry used to re-delete
    // whichever workspace failed most recently, so retrying the FIRST failure
    // would wrongly target the SECOND workspace.
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace("ws-A"), mockWorkspace("ws-B")]);
    const { execute } = renderDeleteHook(store);

    // Both initial deletes reject -> two error toasts (each set on the same atom).
    mockDeleteWorkspace.mockRejectedValue(new Error("network"));

    execute("ws-A", "Workspace A");
    await flushMicrotasks();
    const firstRetry = store.get(workspaceDeleteErrorToastAtom)?.action?.handleClick;

    execute("ws-B", "Workspace B");
    await flushMicrotasks();
    const secondRetry = store.get(workspaceDeleteErrorToastAtom)?.action?.handleClick;

    expect(firstRetry).toBeDefined();
    expect(secondRetry).toBeDefined();
    expect(firstRetry).not.toBe(secondRetry);

    mockDeleteWorkspace.mockClear();
    mockDeleteWorkspace.mockResolvedValue(undefined);

    // Invoke the FIRST failure's Retry. It must re-delete ws-A, not ws-B.
    // (The rollback restored ws-A so the optimistic re-delete proceeds.)
    firstRetry!();
    await flushMicrotasks();

    expect(mockDeleteWorkspace).toHaveBeenCalledTimes(1);
    expect(mockDeleteWorkspace).toHaveBeenCalledWith(
      expect.objectContaining({ path: expect.objectContaining({ workspace_id: "ws-A" }) }),
    );
  });
});
