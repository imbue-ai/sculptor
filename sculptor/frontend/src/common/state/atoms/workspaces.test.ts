import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { Workspace } from "../../../api";
import { updateWorkspace } from "../../../api";
import { workspaceOpenCloseErrorToastAtom } from "./toasts";
import {
  closedWorkspaceIdsAtom,
  closeWorkspaceTabAtom,
  createMigratingTabsStorage,
  effectiveOpenTabIdsAtom,
  INVALID_ACTIVE_INDEX,
  openWorkspaceTabAtom,
  optimisticDeleteWorkspaceAtom,
  tabOrderAtom,
  tabsAtom,
  updateWorkspacesAtom,
  workspaceAtomFamily,
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

describe("closedWorkspaceIdsAtom — pill visibility while close is in flight", () => {
  // See SCU-455: the ClosedWorkspacesPill derives from closedWorkspaceIdsAtom,
  // which today only surfaces workspaces whose backend isOpen has flipped to
  // false. If the websocket is slow, stale, or drops an update, the pill never
  // appears. Including pending-close IDs makes the pill appear instantly and
  // stay stable through any mid-flight stale snapshot.
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(updateWorkspace).mockReturnValue(new Promise(() => {}) as ReturnType<typeof updateWorkspace>);
  });

  afterEach(() => {
    vi.mocked(updateWorkspace).mockReset();
  });

  it("includes the workspace ID the moment close is requested (before any ack)", () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    expect(store.get(closedWorkspaceIdsAtom)).not.toContain("ws-1");

    store.set(closeWorkspaceTabAtom, "ws-1");

    expect(store.get(closedWorkspaceIdsAtom)).toContain("ws-1");
  });

  it("keeps the workspace ID visible as closed even when a stale isOpen=true snapshot arrives", () => {
    const ws = mockWorkspace({ objectId: "ws-1", isOpen: true });
    const store = seedHydratedStore([ws], ["ws-1"]);

    store.set(closeWorkspaceTabAtom, "ws-1");
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "ws-1", isOpen: true })]);

    expect(store.get(closedWorkspaceIdsAtom)).toContain("ws-1");
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

  it("optimisticDeleteWorkspaceAtom resets activeIndex to -1 when the active tab IS the deleted one", () => {
    const store = seedThreeWorkspacesWithActive(1);

    store.set(optimisticDeleteWorkspaceAtom, "ws-b");

    expect(store.get(tabsAtom)).toEqual({
      order: [
        { tabId: "ws-a", agentId: null },
        { tabId: "ws-c", agentId: null },
      ],
      activeIndex: INVALID_ACTIVE_INDEX,
    });
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

  it("strips stale __new_workspace_<draftId>__ ids from an existing sculptor-tabs value and writes it back", () => {
    localStorage.setItem(
      "sculptor-tabs",
      JSON.stringify({
        order: [
          { tabId: "__new_workspace_legacy-draft__", agentId: null },
          { tabId: "ws_a", agentId: "agent-1" },
        ],
        activeIndex: 1,
      }),
    );

    const storage = createMigratingTabsStorage();
    const state = storage.getItem("sculptor-tabs", DEFAULT_STATE);

    // The dead draft id is gone and activeIndex still points at ws_a.
    expect(state).toEqual({
      order: [{ tabId: "ws_a", agentId: "agent-1" }],
      activeIndex: 0,
    });
    // The scrubbed order is persisted so it can never resurface.
    expect(JSON.parse(localStorage.getItem("sculptor-tabs") ?? "null")).toEqual(state);
  });

  it("strips stale __new_workspace_<draftId>__ ids while migrating the legacy key", () => {
    localStorage.setItem("sculptor-tab-order", JSON.stringify(["__new_workspace_legacy-draft__", "__home__", "ws_x"]));

    const storage = createMigratingTabsStorage();
    expect(storage.getItem("sculptor-tabs", DEFAULT_STATE)).toEqual({
      order: [
        { tabId: "__home__", agentId: null },
        { tabId: "ws_x", agentId: null },
      ],
      activeIndex: INVALID_ACTIVE_INDEX,
    });
    expect(localStorage.getItem("sculptor-tab-order")).toBeNull();
  });
});
