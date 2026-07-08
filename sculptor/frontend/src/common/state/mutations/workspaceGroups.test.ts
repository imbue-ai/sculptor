import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { WorkspaceGroup } from "../../../api";
import { queryClient as sharedQueryClient } from "../../queryClient.ts";
import {
  resetWorkspaceGroupSyncVersionsForTesting,
  updateWorkspaceGroupsAtom,
  workspaceGroupAtomFamily,
} from "../atoms/workspaceGroups";
import {
  useAddWorkspaceGroupMemberMutation,
  useCreateWorkspaceGroupMutation,
  useRemoveWorkspaceGroupMemberMutation,
  useUngroupWorkspaceGroupMutation,
  useUpdateWorkspaceGroupMutation,
} from "./workspaceGroups";

// ── Mock API ────────────────────────────────────────────────
const { mockCreate, mockUpdate, mockAddMember, mockRemoveMember, mockUngroup } = vi.hoisted(() => ({
  mockCreate: vi.fn(),
  mockUpdate: vi.fn(),
  mockAddMember: vi.fn(),
  mockRemoveMember: vi.fn(),
  mockUngroup: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    createWorkspaceGroup: mockCreate,
    updateWorkspaceGroup: mockUpdate,
    addWorkspaceGroupMember: mockAddMember,
    removeWorkspaceGroupMember: mockRemoveMember,
    ungroupWorkspaceGroup: mockUngroup,
  };
});

// ── Helpers ─────────────────────────────────────────────────

const GROUP_ID = "wsg-1";
const PROJECT_ID = "p-1";
const WS_ID = "ws-1";

const makeGroup = (overrides: Partial<WorkspaceGroup> = {}): WorkspaceGroup => ({
  objectId: GROUP_ID,
  organizationReference: "org-1",
  projectId: PROJECT_ID,
  name: "Group 1",
  color: "blue",
  createdViaCli: false,
  isDeleted: false,
  createdAt: "2026-01-01T00:00:00Z",
  ...overrides,
});

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

// Each test gets its own Jotai store; the hooks pick it up through the
// Provider (useStore), exactly as the app store reaches them at runtime.
let store: ReturnType<typeof createStore>;

const makeWrapper = () => {
  return ({ children }: { children: ReactNode }): ReactElement =>
    createElement(QueryClientProvider, { client: sharedQueryClient }, createElement(Provider, { store }, children));
};

const seedGroup = (group: WorkspaceGroup): void => {
  store.set(updateWorkspaceGroupsAtom, [group]);
};

const getStoredGroup = (id: string): WorkspaceGroup | null => store.get(workspaceGroupAtomFamily(id));

// ── Lifecycle ───────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockCreate.mockResolvedValue({ data: undefined });
  mockUpdate.mockResolvedValue(undefined);
  mockAddMember.mockResolvedValue(undefined);
  mockRemoveMember.mockResolvedValue(undefined);
  mockUngroup.mockResolvedValue(undefined);
  store = createStore();
  // Sync versions live in a module-level map, so they leak across tests
  // without an explicit reset.
  resetWorkspaceGroupSyncVersionsForTesting();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ═══════════════════════════════════════════════════════════
// useCreateWorkspaceGroupMutation
// ═══════════════════════════════════════════════════════════

describe("useCreateWorkspaceGroupMutation", () => {
  it("calls createWorkspaceGroup with the correct body and resolves the created group", async () => {
    const created = { objectId: GROUP_ID, projectId: PROJECT_ID, name: "Group 1", color: "blue" };
    mockCreate.mockResolvedValueOnce({ data: created });
    const { result } = renderHook(() => useCreateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    let resolved: unknown;
    await act(async () => {
      resolved = await result.current.mutateAsync({ projectId: PROJECT_ID, workspaceIds: [WS_ID] });
    });

    expect(mockCreate).toHaveBeenCalledOnce();
    expect(mockCreate).toHaveBeenCalledWith({
      body: { projectId: PROJECT_ID, workspaceIds: [WS_ID], name: undefined, color: undefined },
    });
    expect(resolved).toEqual(created);
  });

  it("passes an explicit name and color through", async () => {
    const { result } = renderHook(() => useCreateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID, workspaceIds: [WS_ID], name: "Custom", color: "teal" });
    });
    await flushMicrotasks();

    expect(mockCreate).toHaveBeenCalledWith({
      body: { projectId: PROJECT_ID, workspaceIds: [WS_ID], name: "Custom", color: "teal" },
    });
  });

  it("never writes the store — the WS delivers the created group", async () => {
    mockCreate.mockRejectedValueOnce(new Error("workspace_groups_disabled"));
    const { result } = renderHook(() => useCreateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID, workspaceIds: [WS_ID] });
    });
    await flushMicrotasks();

    expect(getStoredGroup(GROUP_ID)).toBeNull();
    expect(result.current.isError).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════
// useUpdateWorkspaceGroupMutation
// ═══════════════════════════════════════════════════════════

describe("useUpdateWorkspaceGroupMutation", () => {
  it("calls updateWorkspaceGroup with the correct path and body", async () => {
    seedGroup(makeGroup());
    const { result } = renderHook(() => useUpdateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID, name: "Renamed" });
    });
    await flushMicrotasks();

    expect(mockUpdate).toHaveBeenCalledOnce();
    expect(mockUpdate).toHaveBeenCalledWith({
      path: { group_id: GROUP_ID },
      body: { name: "Renamed", color: undefined },
    });
  });

  it("optimistically applies the rename and recolor, leaving omitted fields alone", async () => {
    seedGroup(makeGroup({ name: "Original", color: "blue" }));
    const { result } = renderHook(() => useUpdateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID, color: "pink" });
    });

    const stored = getStoredGroup(GROUP_ID);
    expect(stored?.color).toBe("pink");
    expect(stored?.name).toBe("Original");
  });

  it("rolls back the store when the API call rejects", async () => {
    seedGroup(makeGroup({ name: "Keep Me" }));
    mockUpdate.mockRejectedValueOnce(new Error("network"));
    const { result } = renderHook(() => useUpdateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID, name: "Bad Rename" });
    });
    await flushMicrotasks();

    expect(getStoredGroup(GROUP_ID)?.name).toBe("Keep Me");
  });

  it("skips the rollback when a WS frame wrote the group while the request was in flight", async () => {
    seedGroup(makeGroup({ name: "Original" }));
    const serverGroup = makeGroup({ name: "Renamed Elsewhere" });
    mockUpdate.mockImplementationOnce(() => {
      // The frame is authoritative: it must survive the failed request's
      // rollback (the delta stream will not re-send an unchanged group).
      store.set(updateWorkspaceGroupsAtom, [serverGroup]);
      return Promise.reject(new Error("network"));
    });

    const { result } = renderHook(() => useUpdateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID, name: "Bad Rename" });
    });
    await flushMicrotasks();

    expect(getStoredGroup(GROUP_ID)).toEqual(serverGroup);
  });

  it("does nothing for a group the stream has not delivered", async () => {
    mockUpdate.mockRejectedValueOnce(new Error("network"));
    const { result } = renderHook(() => useUpdateWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: "wsg-missing", name: "Nope" });
    });
    await flushMicrotasks();

    expect(getStoredGroup("wsg-missing")).toBeNull();
  });
});

// ═══════════════════════════════════════════════════════════
// Membership and ungroup mutations (no optimistic writes)
// ═══════════════════════════════════════════════════════════

describe("useAddWorkspaceGroupMemberMutation", () => {
  it("calls addWorkspaceGroupMember with the correct path and body", async () => {
    const { result } = renderHook(() => useAddWorkspaceGroupMemberMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID, workspaceId: WS_ID });
    });
    await flushMicrotasks();

    expect(mockAddMember).toHaveBeenCalledOnce();
    expect(mockAddMember).toHaveBeenCalledWith({
      path: { group_id: GROUP_ID },
      body: { workspaceId: WS_ID },
    });
  });
});

describe("useRemoveWorkspaceGroupMemberMutation", () => {
  it("calls removeWorkspaceGroupMember with the correct path", async () => {
    const { result } = renderHook(() => useRemoveWorkspaceGroupMemberMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID, workspaceId: WS_ID });
    });
    await flushMicrotasks();

    expect(mockRemoveMember).toHaveBeenCalledOnce();
    expect(mockRemoveMember).toHaveBeenCalledWith({
      path: { group_id: GROUP_ID, workspace_id: WS_ID },
    });
  });
});

describe("useUngroupWorkspaceGroupMutation", () => {
  it("calls ungroupWorkspaceGroup with the correct path", async () => {
    const { result } = renderHook(() => useUngroupWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID });
    });
    await flushMicrotasks();

    expect(mockUngroup).toHaveBeenCalledOnce();
    expect(mockUngroup).toHaveBeenCalledWith({ path: { group_id: GROUP_ID } });
  });

  it("never writes the store on failure — the group stays until the WS deletes it", async () => {
    seedGroup(makeGroup());
    mockUngroup.mockRejectedValueOnce(new Error("network"));
    const { result } = renderHook(() => useUngroupWorkspaceGroupMutation(), { wrapper: makeWrapper() });

    act(() => {
      result.current.mutate({ groupId: GROUP_ID });
    });
    await flushMicrotasks();

    expect(getStoredGroup(GROUP_ID)).toEqual(makeGroup());
    expect(result.current.isError).toBe(true);
  });
});
