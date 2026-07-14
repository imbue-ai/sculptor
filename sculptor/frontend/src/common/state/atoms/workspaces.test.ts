import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView, Workspace } from "../../../api";
import { TaskStatus, updateWorkspace } from "../../../api";
import { taskAtomFamily, taskIdsAtom } from "./tasks.ts";
import { workspaceOpenCloseErrorToastAtom } from "./toasts";
import {
  closeWorkspaceTabAtom,
  createMigratingTabsStorage,
  effectiveOpenTabIdsAtom,
  getWorkspaceSyncVersion,
  INVALID_ACTIVE_INDEX,
  isWorkspaceKnownAtomFamily,
  openWorkspaceTabAtom,
  optimisticDeleteWorkspaceAtom,
  rollbackDeleteWorkspaceAtom,
  tabOrderAtom,
  tabsAtom,
  tombstonedWorkspaceIdsAtom,
  updateWorkspacesAtom,
  workspaceAtomFamily,
  workspaceDotStatusAtomFamily,
  workspaceIdsAtom,
} from "./workspaces";

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    updateWorkspace: vi.fn().mockResolvedValue({ data: {} }),
    batchUpdateOpenState: vi.fn().mockResolvedValue({ data: {} }),
  };
});

const mockWorkspace = (overrides: Partial<Workspace> & Pick<Workspace, "objectId">): Workspace =>
  ({
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "",
    initializationStrategy: "CLONE",
    isOpen: true,
    isDeleted: false,
    ...overrides,
  }) as Workspace;

const flushMicrotasks = async (): Promise<void> => {
  // Promise.resolve().then().then()… schedules microtasks; awaiting a macrotask
  // drains any chained .then/.catch/.finally queued by the atom under test.
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const seedHydratedStore = (
  workspaces: ReadonlyArray<Workspace>,
  tabOrder: ReadonlyArray<string>,
): ReturnType<typeof createStore> => {
  const store = createStore();
  // updateWorkspacesAtom hydrates workspace atoms + flips hasHydratedWorkspaceTabsAtom,
  // mirroring what the real websocket stream does on first message.
  store.set(updateWorkspacesAtom, workspaces);
  store.set(tabsAtom, {
    order: tabOrder.map((tabId) => ({ tabId, agentId: null })),
    activeIndex: INVALID_ACTIVE_INDEX,
  });
  return store;
};

describe("closeWorkspaceTabAtom", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(updateWorkspace).mockResolvedValue({ data: {} } as Awaited<ReturnType<typeof updateWorkspace>>);
  });

  afterEach(() => {
    vi.mocked(updateWorkspace).mockReset();
  });

  it("calls updateWorkspace with isOpen=false for real workspace IDs", () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    store.set(closeWorkspaceTabAtom, "ws-1");

    expect(vi.mocked(updateWorkspace)).toHaveBeenCalledWith({
      path: { workspace_id: "ws-1" },
      body: { isOpen: false },
    });
  });

  it("removes pseudo-tabs from tabOrderAtom synchronously without calling the API", () => {
    const store = createStore();
    store.set(tabsAtom, {
      order: [
        { tabId: "__home__", agentId: null },
        { tabId: "__settings__", agentId: null },
      ],
      activeIndex: INVALID_ACTIVE_INDEX,
    });

    store.set(closeWorkspaceTabAtom, "__settings__");

    expect(store.get(tabOrderAtom)).toEqual(["__home__"]);
    expect(vi.mocked(updateWorkspace)).not.toHaveBeenCalled();
  });

  it("hides the tab immediately even if a stale websocket snapshot arrives before the ack", () => {
    // This is the flicker bug: the user closes W, a websocket snapshot generated
    // BEFORE the backend processed the close arrives (still carrying isOpen=true),
    // and the tab flicks back into existence until the post-close snapshot arrives.
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    // Never-resolving API so the close is "in flight" for the rest of the test.
    vi.mocked(updateWorkspace).mockReturnValue(new Promise(() => {}) as ReturnType<typeof updateWorkspace>);

    store.set(closeWorkspaceTabAtom, "ws-1");
    // Stale snapshot arrives during the in-flight window.
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: true })]);

    expect(store.get(effectiveOpenTabIdsAtom)).not.toContain("ws-1");
  });

  it("sets the error toast when the close API call fails", async () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    vi.mocked(updateWorkspace).mockRejectedValue(new Error("boom"));

    store.set(closeWorkspaceTabAtom, "ws-1");
    await flushMicrotasks();

    expect(store.get(workspaceOpenCloseErrorToastAtom)).not.toBeNull();
  });

  it("un-hides the tab after a failed close so it's visible again", async () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    vi.mocked(updateWorkspace).mockRejectedValue(new Error("boom"));

    store.set(closeWorkspaceTabAtom, "ws-1");
    // Before the rejection resolves, the tab is hidden (pending-close suppression).
    expect(store.get(effectiveOpenTabIdsAtom)).not.toContain("ws-1");

    await flushMicrotasks();

    // After rejection, suppression is cleared; openWorkspaceIdsAtom still has the
    // workspace (the backend never confirmed the close), so the tab reappears.
    expect(store.get(effectiveOpenTabIdsAtom)).toContain("ws-1");
  });

  it("keeps the tab hidden when a stale isOpen=true snapshot arrives after a successful close", async () => {
    // Regression test for SCU-455: a slow-to-arrive earlier-open PATCH response
    // can land after our close ack, carrying isOpen=true. The suppression must
    // override that stale snapshot.
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    store.set(closeWorkspaceTabAtom, "ws-1");
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: false })]);
    await flushMicrotasks();
    expect(store.get(effectiveOpenTabIdsAtom)).not.toContain("ws-1");

    // Stale isOpen=true snapshot arrives later — should be overridden to false
    // by the persistent pending-close suppression.
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: true })]);
    expect(store.get(effectiveOpenTabIdsAtom)).not.toContain("ws-1");
    expect(store.get(workspaceAtomFamily("ws-1"))?.isOpen).toBe(false);
  });

  it("lets the user reopen the workspace via openWorkspaceTabAtom (clears suppression)", async () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    store.set(closeWorkspaceTabAtom, "ws-1");
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: false })]);
    await flushMicrotasks();
    expect(store.get(effectiveOpenTabIdsAtom)).not.toContain("ws-1");

    store.set(openWorkspaceTabAtom, "ws-1");
    // Subsequent isOpen=true snapshot should now apply normally.
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: true })]);
    expect(store.get(effectiveOpenTabIdsAtom)).toContain("ws-1");
  });
});

describe("openWorkspaceTabAtom", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(updateWorkspace).mockResolvedValue({ data: {} } as Awaited<ReturnType<typeof updateWorkspace>>);
  });

  afterEach(() => {
    vi.mocked(updateWorkspace).mockReset();
  });

  it("adds the workspace to tabOrderAtom and calls updateWorkspace with isOpen=true", () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: false });
    const store = seedHydratedStore([ws], []);

    store.set(openWorkspaceTabAtom, "ws-1");

    expect(store.get(tabOrderAtom)).toContain("ws-1");
    expect(vi.mocked(updateWorkspace)).toHaveBeenCalledWith({
      path: { workspace_id: "ws-1" },
      body: { isOpen: true },
    });
  });

  it("rolls back the tab order insert when the open API call fails", async () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: false });
    const store = seedHydratedStore([ws], []);

    vi.mocked(updateWorkspace).mockRejectedValue(new Error("boom"));

    store.set(openWorkspaceTabAtom, "ws-1");
    expect(store.get(tabOrderAtom)).toContain("ws-1");

    await flushMicrotasks();

    expect(store.get(tabOrderAtom)).not.toContain("ws-1");
  });

  it("sets the error toast when the open API call fails", async () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: false });
    const store = seedHydratedStore([ws], []);

    vi.mocked(updateWorkspace).mockRejectedValue(new Error("boom"));

    store.set(openWorkspaceTabAtom, "ws-1");
    await flushMicrotasks();

    expect(store.get(workspaceOpenCloseErrorToastAtom)).not.toBeNull();
  });

  it("does not roll back the tab order when the open API call succeeds", async () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: false });
    const store = seedHydratedStore([ws], []);

    store.set(openWorkspaceTabAtom, "ws-1");
    await flushMicrotasks();

    expect(store.get(tabOrderAtom)).toContain("ws-1");
  });
});

describe("seedHydratedStore sanity", () => {
  it("hydrates workspace atoms so effectiveOpenTabIdsAtom sees the workspace as open", () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    expect(store.get(workspaceIdsAtom)).toContain("ws-1");
    expect(store.get(workspaceAtomFamily("ws-1"))).toEqual(ws);
    expect(store.get(effectiveOpenTabIdsAtom)).toContain("ws-1");
  });
});

describe("updateWorkspacesAtom skip-unchanged writes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(updateWorkspace).mockResolvedValue({ data: {} } as Awaited<ReturnType<typeof updateWorkspace>>);
  });

  it("does not notify a workspace's subscribers when a byte-identical frame is re-sent", () => {
    const store = seedHydratedStore([mockWorkspace({ objectId: "ws-1", isOpen: true })], ["ws-1"]);
    const listener = vi.fn();
    const unsubscribe = store.sub(workspaceAtomFamily("ws-1"), listener);

    // A fresh Workspace object with identical fields — the deep-equality write
    // skip must swallow it so the row/header/peek don't re-render every frame.
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: true })]);
    expect(listener).not.toHaveBeenCalled();

    // A genuinely changed field still writes through.
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: true, description: "changed" })]);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("does not notify workspaceIdsAtom subscribers when the id membership is unchanged", () => {
    const store = seedHydratedStore([mockWorkspace({ objectId: "ws-1", isOpen: true })], ["ws-1"]);
    const listener = vi.fn();
    const unsubscribe = store.sub(workspaceIdsAtom, listener);

    // Re-sending the same workspace rebuilds the ids array with identical
    // membership; the membership-equality skip must not publish a fresh array.
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: true })]);
    expect(listener).not.toHaveBeenCalled();

    // A new workspace changes membership and must notify.
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-2", isOpen: true })]);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});

describe("activeIndex clamping on workspace deletion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(updateWorkspace).mockResolvedValue({ data: {} } as Awaited<ReturnType<typeof updateWorkspace>>);
  });

  const seedThreeWorkspacesWithActive = (activeIndex: number): ReturnType<typeof createStore> => {
    const ws = ["ws-a", "ws-b", "ws-c"].map((id) => mockWorkspace({ objectId: id, isOpen: true }));
    const store = seedHydratedStore(ws, ["ws-a", "ws-b", "ws-c"]);
    store.set(tabsAtom, {
      order: [
        { tabId: "ws-a", agentId: null },
        { tabId: "ws-b", agentId: null },
        { tabId: "ws-c", agentId: null },
      ],
      activeIndex,
    });
    return store;
  };

  it("optimisticDeleteWorkspaceAtom keeps activeIndex unchanged when the active tab is BEFORE the deleted one", () => {
    const store = seedThreeWorkspacesWithActive(0);

    store.set(optimisticDeleteWorkspaceAtom, "ws-c");

    expect(store.get(tabsAtom)).toEqual({
      order: [
        { tabId: "ws-a", agentId: null },
        { tabId: "ws-b", agentId: null },
      ],
      activeIndex: 0,
    });
  });

  it("optimisticDeleteWorkspaceAtom clamps activeIndex to the tab filling the deleted slot when the active tab IS the deleted one", () => {
    const store = seedThreeWorkspacesWithActive(1);

    store.set(optimisticDeleteWorkspaceAtom, "ws-b");

    // The active tab was removed; rather than leave activeIndex at the invalid
    // sentinel (which makes a reload's rootLoader bounce to /ws/new), it is
    // clamped to a surviving neighbor — the tab that shifts into the deleted
    // slot (ws-c at index 1). The follow-up navigation refines this further.
    expect(store.get(tabsAtom)).toEqual({
      order: [
        { tabId: "ws-a", agentId: null },
        { tabId: "ws-c", agentId: null },
      ],
      activeIndex: 1,
    });
  });

  it("optimisticDeleteWorkspaceAtom clamps to the new last tab when the active (and last) tab is deleted", () => {
    const store = seedThreeWorkspacesWithActive(2);

    store.set(optimisticDeleteWorkspaceAtom, "ws-c");

    expect(store.get(tabsAtom)).toEqual({
      order: [
        { tabId: "ws-a", agentId: null },
        { tabId: "ws-b", agentId: null },
      ],
      activeIndex: 1,
    });
  });

  it("optimisticDeleteWorkspaceAtom leaves activeIndex invalid when the last remaining tab is deleted", () => {
    const ws = [mockWorkspace({ objectId: "ws-only", isOpen: true })];
    const store = seedHydratedStore(ws, ["ws-only"]);
    store.set(tabsAtom, { order: [{ tabId: "ws-only", agentId: null }], activeIndex: 0 });

    store.set(optimisticDeleteWorkspaceAtom, "ws-only");

    expect(store.get(tabsAtom)).toEqual({ order: [], activeIndex: INVALID_ACTIVE_INDEX });
  });

  it("optimisticDeleteWorkspaceAtom decrements activeIndex when the active tab is AFTER the deleted one", () => {
    const store = seedThreeWorkspacesWithActive(2);

    store.set(optimisticDeleteWorkspaceAtom, "ws-a");

    expect(store.get(tabsAtom)).toEqual({
      order: [
        { tabId: "ws-b", agentId: null },
        { tabId: "ws-c", agentId: null },
      ],
      activeIndex: 1,
    });
  });

  it("updateWorkspacesAtom isDeleted branch removes the entry and clamps activeIndex", () => {
    const store = seedThreeWorkspacesWithActive(2);

    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-b", isDeleted: true })]);

    expect(store.get(tabsAtom)).toEqual({
      order: [
        { tabId: "ws-a", agentId: null },
        { tabId: "ws-c", agentId: null },
      ],
      activeIndex: 1,
    });
  });

  it("updateWorkspacesAtom isDeleted branch lands activeIndex on a neighbor when the ACTIVE tab is deleted", () => {
    // A delete confirmed by the server (e.g. from another client) takes the
    // same applyClose path as an optimistic delete, so deleting the active tab
    // must not leave the persisted activeIndex at the invalid sentinel either.
    const store = seedThreeWorkspacesWithActive(1);

    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-b", isDeleted: true })]);

    expect(store.get(tabsAtom)).toEqual({
      order: [
        { tabId: "ws-a", agentId: null },
        { tabId: "ws-c", agentId: null },
      ],
      activeIndex: 1,
    });
  });

  it("closeWorkspaceTabAtom does NOT touch activeIndex for real workspace tabs (close is reversible)", () => {
    const store = seedThreeWorkspacesWithActive(1);

    store.set(closeWorkspaceTabAtom, "ws-a");

    // The entry stays in order so the tab can be re-opened; activeIndex is untouched.
    expect(store.get(tabsAtom).order).toEqual([
      { tabId: "ws-a", agentId: null },
      { tabId: "ws-b", agentId: null },
      { tabId: "ws-c", agentId: null },
    ]);
    expect(store.get(tabsAtom).activeIndex).toBe(1);
  });
});

describe("createMigratingTabsStorage", () => {
  const DEFAULT_STATE = { order: [], activeIndex: INVALID_ACTIVE_INDEX };

  beforeEach(() => {
    localStorage.removeItem("sculptor-tabs");
    localStorage.removeItem("sculptor-tab-order");
  });

  it("migrates a legacy sculptor-tab-order array on first read and clears the legacy key", () => {
    localStorage.setItem("sculptor-tab-order", JSON.stringify(["__home__", "ws_x"]));

    const storage = createMigratingTabsStorage();
    const state = storage.getItem("sculptor-tabs", DEFAULT_STATE);

    expect(state).toEqual({
      order: [
        { tabId: "__home__", agentId: null },
        { tabId: "ws_x", agentId: null },
      ],
      activeIndex: INVALID_ACTIVE_INDEX,
    });
    expect(localStorage.getItem("sculptor-tab-order")).toBeNull();
    expect(JSON.parse(localStorage.getItem("sculptor-tabs") ?? "null")).toEqual(state);
  });

  it("uses an existing sculptor-tabs value verbatim and ignores any stale legacy key", () => {
    const persisted = {
      order: [{ tabId: "ws_y", agentId: "agent-1" }],
      activeIndex: 0,
    };
    localStorage.setItem("sculptor-tabs", JSON.stringify(persisted));
    localStorage.setItem("sculptor-tab-order", JSON.stringify(["should-be-ignored"]));

    const storage = createMigratingTabsStorage();
    expect(storage.getItem("sculptor-tabs", DEFAULT_STATE)).toEqual(persisted);
  });

  it("falls back to the default state when no keys are present", () => {
    const storage = createMigratingTabsStorage();
    expect(storage.getItem("sculptor-tabs", DEFAULT_STATE)).toEqual(DEFAULT_STATE);
  });

  it("falls back to the default state when sculptor-tabs is malformed and no legacy key exists", () => {
    localStorage.setItem("sculptor-tabs", "{not json");

    const storage = createMigratingTabsStorage();
    expect(storage.getItem("sculptor-tabs", DEFAULT_STATE)).toEqual(DEFAULT_STATE);
  });

  it("migrates from the legacy key when sculptor-tabs is malformed", () => {
    localStorage.setItem("sculptor-tabs", "{not json");
    localStorage.setItem("sculptor-tab-order", JSON.stringify(["__home__"]));

    const storage = createMigratingTabsStorage();
    expect(storage.getItem("sculptor-tabs", DEFAULT_STATE)).toEqual({
      order: [{ tabId: "__home__", agentId: null }],
      activeIndex: INVALID_ACTIVE_INDEX,
    });
    expect(localStorage.getItem("sculptor-tab-order")).toBeNull();
  });

  it("skips non-string entries in the legacy array without crashing", () => {
    localStorage.setItem("sculptor-tab-order", JSON.stringify(["__home__", 42, null, "ws_a"]));

    const storage = createMigratingTabsStorage();
    expect(storage.getItem("sculptor-tabs", DEFAULT_STATE)).toEqual({
      order: [
        { tabId: "__home__", agentId: null },
        { tabId: "ws_a", agentId: null },
      ],
      activeIndex: INVALID_ACTIVE_INDEX,
    });
  });
});

describe("isWorkspaceKnownAtomFamily", () => {
  it("is undefined before the first workspace snapshot arrives", () => {
    const store = createStore();
    expect(store.get(isWorkspaceKnownAtomFamily("w1"))).toBeUndefined();
  });

  it("reports membership once the id list is loaded", () => {
    const store = createStore();
    store.set(workspaceIdsAtom, ["w1"]);
    expect(store.get(isWorkspaceKnownAtomFamily("w1"))).toBe(true);
    expect(store.get(isWorkspaceKnownAtomFamily("w2"))).toBe(false);
  });

  it("does not notify subscribers when the id array is rebuilt with the same membership", () => {
    const store = createStore();
    store.set(workspaceIdsAtom, ["w1", "w2"]);
    const listener = vi.fn();
    const unsubscribe = store.sub(isWorkspaceKnownAtomFamily("w1"), listener);

    // A fresh array identity with identical contents — the boolean slice
    // resolves to the same primitive, so no notification is expected.
    store.set(workspaceIdsAtom, ["w1", "w2"]);
    expect(listener).not.toHaveBeenCalled();

    store.set(workspaceIdsAtom, ["w2"]);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});

describe("workspaceDotStatusAtomFamily", () => {
  const dotTask = (
    id: string,
    workspaceId: string,
    overrides: Partial<CodingAgentTaskView> = {},
  ): CodingAgentTaskView =>
    ({
      id,
      workspaceId,
      status: TaskStatus.RUNNING,
      lastReadAt: "2026-01-02T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
      isDeleted: false,
      isArchived: false,
      ...overrides,
    }) as CodingAgentTaskView;

  it("aggregates only the workspace's own tasks", () => {
    const store = createStore();
    store.set(taskIdsAtom, ["t1", "t2"]);
    store.set(taskAtomFamily("t1"), dotTask("t1", "ws-a"));
    store.set(taskAtomFamily("t2"), dotTask("t2", "ws-b", { status: TaskStatus.ERROR }));

    expect(store.get(workspaceDotStatusAtomFamily("ws-a"))).toMatchObject({ hasRunning: true, hasError: false });
    expect(store.get(workspaceDotStatusAtomFamily("ws-b"))).toMatchObject({ hasRunning: false, hasError: true });
  });

  it("keeps reference identity across a task tick that does not flip any flag", () => {
    const store = createStore();
    store.set(taskIdsAtom, ["t1"]);
    store.set(taskAtomFamily("t1"), dotTask("t1", "ws-a"));

    const first = store.get(workspaceDotStatusAtomFamily("ws-a"));
    store.set(taskAtomFamily("t1"), dotTask("t1", "ws-a", { title: "tick" }));

    expect(store.get(workspaceDotStatusAtomFamily("ws-a"))).toBe(first);
  });

  it("notifies subscribers when an aggregate flag flips", () => {
    const store = createStore();
    store.set(taskIdsAtom, ["t1"]);
    store.set(taskAtomFamily("t1"), dotTask("t1", "ws-a"));
    const listener = vi.fn();
    const unsubscribe = store.sub(workspaceDotStatusAtomFamily("ws-a"), listener);

    store.set(taskAtomFamily("t1"), dotTask("t1", "ws-a", { status: TaskStatus.WAITING }));

    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.get(workspaceDotStatusAtomFamily("ws-a"))).toMatchObject({ hasRunning: false, hasWaiting: true });
    unsubscribe();
  });
});

describe("workspace sync versions and the tombstone derivation (SCU-1834)", () => {
  it("bumps the sync version for every workspace a frame carries, including deletions", () => {
    const store = createStore();
    const before = getWorkspaceSyncVersion("ws-1");

    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1" })]);
    expect(getWorkspaceSyncVersion("ws-1")).toBe(before + 1);

    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isDeleted: true })]);
    expect(getWorkspaceSyncVersion("ws-1")).toBe(before + 2);
  });

  it("derives the tombstoned set: ids the store knows but holds as null", () => {
    const store = seedHydratedStore([mockWorkspace({ objectId: "ws-1" })], ["ws-1"]);
    expect(store.get(tombstonedWorkspaceIdsAtom).has("ws-1")).toBe(false);

    store.set(optimisticDeleteWorkspaceAtom, "ws-1");
    expect(store.get(tombstonedWorkspaceIdsAtom).has("ws-1")).toBe(true);

    // Ids the store never loaded are not tombstones — they are simply unknown.
    expect(store.get(tombstonedWorkspaceIdsAtom).has("ws-unknown")).toBe(false);
  });

  it("rolls back symmetrically: the workspace atom and the tombstone clear together", () => {
    const store = seedHydratedStore([mockWorkspace({ objectId: "ws-1" })], ["ws-1"]);
    const context = store.set(optimisticDeleteWorkspaceAtom, "ws-1");
    expect(store.get(tombstonedWorkspaceIdsAtom).has("ws-1")).toBe(true);

    store.set(rollbackDeleteWorkspaceAtom, { workspaceId: "ws-1", context });

    expect(store.get(workspaceAtomFamily("ws-1"))).not.toBeNull();
    expect(store.get(tombstonedWorkspaceIdsAtom).has("ws-1")).toBe(false);
  });

  it("returns a request-worthy context even when the store does not know the workspace", () => {
    const store = createStore();
    const context = store.set(optimisticDeleteWorkspaceAtom, "ws-ghost");

    // No snapshot means nothing was applied and rollback is a no-op — but the
    // caller still has a context to thread through the mutation.
    expect(context.snapshot).toBeNull();
    store.set(rollbackDeleteWorkspaceAtom, { workspaceId: "ws-ghost", context });
    expect(store.get(workspaceAtomFamily("ws-ghost"))).toBeNull();
  });

  it("yields the rollback when an authoritative frame bumped the version mid-request", () => {
    const store = seedHydratedStore([mockWorkspace({ objectId: "ws-1", description: "stale" })], ["ws-1"]);
    const context = store.set(optimisticDeleteWorkspaceAtom, "ws-1");

    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", description: "fresh" })]);
    store.set(rollbackDeleteWorkspaceAtom, { workspaceId: "ws-1", context });

    expect(store.get(workspaceAtomFamily("ws-1"))?.description).toBe("fresh");
  });

  it("does not notify tombstone subscribers when a frame leaves the set unchanged", () => {
    const store = seedHydratedStore([mockWorkspace({ objectId: "ws-1" })], ["ws-1"]);
    store.get(tombstonedWorkspaceIdsAtom);
    const listener = vi.fn();
    const unsubscribe = store.sub(tombstonedWorkspaceIdsAtom, listener);

    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", description: "tick" })]);

    expect(listener).not.toHaveBeenCalled();
    unsubscribe();
  });
});
