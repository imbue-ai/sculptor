import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily, atomWithStorage, createJSONStorage } from "jotai/utils";

import type { Workspace } from "../../../api";
import { batchUpdateOpenState, updateWorkspace as updateWorkspaceApi } from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { invalidateWorkspaceGitQueries, removeWorkspaceQueriesCache } from "../../queryClient.ts";
import { workspaceOpenCloseErrorToastAtom } from "./toasts";
import { workspaceSetupStatusAtomFamily } from "./workspaceSetupStatus";

export const workspaceAtomFamily = atomFamily<string, PrimitiveAtom<Workspace | null>>(() =>
  atom<Workspace | null>(null),
);

export const workspaceIdsAtom = atom<ReadonlyArray<string> | undefined>(undefined);

/**
 * Tracks workspace IDs that have been optimistically deleted in the current
 * session.  Components that maintain their own workspace lists (e.g.
 * RecentWorkspaces) can subscribe to this atom to filter out deleted
 * workspaces without needing a page reload.
 */
export const deletedWorkspaceIdsAtom = atom<ReadonlySet<string>>(new Set<string>());

export const workspacesArrayAtom = atom<ReadonlyArray<Workspace> | undefined>((get) => {
  const workspaceIds = get(workspaceIdsAtom);
  if (workspaceIds === undefined) {
    return undefined;
  }
  return workspaceIds
    .map((id) => get(workspaceAtomFamily(id)))
    .filter((workspace): workspace is Workspace => workspace !== null && !workspace.isDeleted);
});

/**
 * Whether there are no (non-deleted) workspaces — the not-yet-loaded window is
 * treated as empty (`?? 0`) so it stays consistent with the empty-Home inline
 * form and the hidden topbar "+". Derived so consumers that only care about the
 * empty state (the new-workspace entry-point gate) re-render only when the
 * emptiness flips, not on every workspace add / remove / status change.
 */
export const isWorkspaceListEmptyAtom = atom<boolean>((get) => {
  const workspaces = get(workspacesArrayAtom);
  return (workspaces?.length ?? 0) === 0;
});

/**
 * IDs of workspaces the backend considers open, derived from workspace models.
 * This is the source of truth for the open/closed SET — the backend owns it.
 */
const openWorkspaceIdsAtom = atom<ReadonlyArray<string>>((get) => {
  const workspaces = get(workspacesArrayAtom);
  if (workspaces === undefined) return [];
  return workspaces.filter((ws) => ws.isOpen !== false).map((ws) => ws.objectId);
});

/** Sentinel `activeIndex` meaning "no MRU pointer" — rootLoader sends user to /home. */
export const INVALID_ACTIVE_INDEX = -1;

export type TabEntry = { tabId: string; agentId: string | null };
export type TabsState = { order: Array<TabEntry>; activeIndex: number };

const LEGACY_TAB_ORDER_KEY = "sculptor-tab-order";

const isValidTabsState = (value: unknown): value is TabsState => {
  if (value === null || typeof value !== "object") return false;
  const v = value as { order?: unknown; activeIndex?: unknown };
  if (!Array.isArray(v.order) || typeof v.activeIndex !== "number") return false;
  for (const entry of v.order) {
    if (entry === null || typeof entry !== "object") return false;
    const e = entry as { tabId?: unknown; agentId?: unknown };
    if (typeof e.tabId !== "string") return false;
    if (e.agentId !== null && typeof e.agentId !== "string") return false;
  }
  return true;
};

/**
 * Prefix of the legacy `__new_workspace_<draftId>__` pseudo-tab IDs. The
 * pseudo-tab system was replaced by the New Workspace modal; pre-modal
 * sessions can still leave these dead IDs in the persisted tab order, so the
 * storage boundary strips them on load (see `scrubDeadTabIds`). Module-private
 * — nothing downstream should produce or match these IDs anymore.
 */
const NEW_WORKSPACE_TAB_PREFIX = "__new_workspace_";

/**
 * Drop dead `__new_workspace_<draftId>__` pseudo-tab IDs from a persisted
 * TabsState, keeping `activeIndex` pointed at the same surviving entry.
 * Returns the input unchanged when there is nothing to strip.
 */
const scrubDeadTabIds = (state: TabsState): TabsState => {
  const order = state.order.filter((e) => !e.tabId.startsWith(NEW_WORKSPACE_TAB_PREFIX));
  if (order.length === state.order.length) return state;
  const activeTabId =
    state.activeIndex >= 0 && state.activeIndex < state.order.length ? state.order[state.activeIndex].tabId : null;
  const activeIndex = activeTabId === null ? INVALID_ACTIVE_INDEX : order.findIndex((e) => e.tabId === activeTabId);
  return { order, activeIndex };
};

/**
 * Storage wrapper for `tabsAtom` that performs a one-time migration from the
 * legacy flat `sculptor-tab-order` array to the new `sculptor-tabs` shape on
 * the first read.  After migration, the legacy key is removed.  All other
 * operations defer to Jotai's standard JSON storage (so cross-tab `subscribe`
 * keeps working).  Exported for unit testing.
 */
export const createMigratingTabsStorage = (): ReturnType<typeof createJSONStorage<TabsState>> => {
  const base = createJSONStorage<TabsState>(() => localStorage);
  return {
    ...base,
    getItem: (key: string, initialValue: TabsState): TabsState => {
      try {
        const raw = localStorage.getItem(key);
        if (raw !== null) {
          try {
            const parsed: unknown = JSON.parse(raw);
            if (isValidTabsState(parsed)) {
              // Strip any dead `__new_workspace_*__` IDs left by pre-modal
              // sessions, and persist the cleaned order so they never resurface.
              const scrubbed = scrubDeadTabIds(parsed);
              if (scrubbed !== parsed) {
                localStorage.setItem(key, JSON.stringify(scrubbed));
              }
              return scrubbed;
            }
          } catch (e) {
            console.warn("[tabsAtom] sculptor-tabs is malformed, falling back to legacy key:", e);
          }
        }
        const legacyRaw = localStorage.getItem(LEGACY_TAB_ORDER_KEY);
        if (legacyRaw !== null) {
          try {
            const legacy: unknown = JSON.parse(legacyRaw);
            if (Array.isArray(legacy)) {
              const order: Array<TabEntry> = legacy
                .filter((id): id is string => typeof id === "string")
                .map((tabId) => ({ tabId, agentId: null }));
              const migrated: TabsState = scrubDeadTabIds({ order, activeIndex: INVALID_ACTIVE_INDEX });
              localStorage.setItem(key, JSON.stringify(migrated));
              localStorage.removeItem(LEGACY_TAB_ORDER_KEY);
              return migrated;
            }
          } catch (e) {
            console.warn("[tabsAtom] legacy sculptor-tab-order is malformed:", e);
          }
          localStorage.removeItem(LEGACY_TAB_ORDER_KEY);
        }
      } catch (e) {
        console.warn("[tabsAtom] failed to read storage:", e);
      }
      return initialValue;
    },
  };
};

/**
 * Persisted tab state: the ordered list of open tabs (workspace IDs +
 * pseudo-tab IDs), an activeIndex pointer that restores the user's last-
 * viewed tab on app restart, and per-workspace last-viewed agent IDs so
 * the rootLoader can navigate directly to /ws/<wsId>/agent/<agentId>
 * without an HTTP roundtrip. The order/activeIndex pair is updated
 * atomically so they cannot disagree.
 */
export const tabsAtom = atomWithStorage<TabsState>(
  "sculptor-tabs",
  { order: [], activeIndex: INVALID_ACTIVE_INDEX },
  createMigratingTabsStorage(),
  { getOnInit: true },
);

/**
 * Read-only view of the tab display order as a flat array of tab IDs.
 * Many callers still treat tab order as `Array<string>`; this preserves
 * their API while the underlying state lives in `tabsAtom`.
 */
export const tabOrderAtom = atom<Array<string>>((get) => get(tabsAtom).order.map((e) => e.tabId));

/**
 * Tracks whether the initial WebSocket snapshot has been reconciled with
 * the persisted tab order. Prevents tab order issues on app restart.
 */
const hasHydratedWorkspaceTabsAtom = atom<boolean>(false);

/** Check whether a tab ID is a pseudo-tab (not a real workspace ID). */
const isPseudoTabId = (id: string): boolean =>
  id === "__settings__" || id === "__component_gallery__" || id === "__home__";

const applyClose = (state: TabsState, tabId: string): TabsState => {
  const removedIndex = state.order.findIndex((e) => e.tabId === tabId);
  if (removedIndex === -1) return state;
  const order = state.order.filter((_, i) => i !== removedIndex);
  let activeIndex = state.activeIndex;
  if (state.activeIndex === removedIndex) {
    activeIndex = INVALID_ACTIVE_INDEX;
  } else if (state.activeIndex > removedIndex) {
    activeIndex = state.activeIndex - 1;
  }
  return { order, activeIndex };
};

const applyOpen = (state: TabsState, entry: TabEntry, options: { setActive: boolean }): TabsState => {
  const existingIndex = state.order.findIndex((e) => e.tabId === entry.tabId);
  if (existingIndex !== -1) {
    if (options.setActive && state.activeIndex !== existingIndex) {
      return { ...state, activeIndex: existingIndex };
    }
    return state;
  }
  const order = [...state.order, entry];
  const activeIndex = options.setActive ? order.length - 1 : state.activeIndex;
  return { order, activeIndex };
};

const applySetActive = (state: TabsState, tabId: string): TabsState => {
  const idx = state.order.findIndex((e) => e.tabId === tabId);
  if (idx === -1 || idx === state.activeIndex) return state;
  return { ...state, activeIndex: idx };
};

const applySetAgent = (state: TabsState, wsId: string, agentId: string | null): TabsState => {
  const idx = state.order.findIndex((e) => e.tabId === wsId);
  if (idx === -1) return state;
  if (state.order[idx].agentId === agentId) return state;
  const order = state.order.slice();
  order[idx] = { ...order[idx], agentId };
  return { ...state, order };
};

const applyReorder = (state: TabsState, newTabIds: Array<string>): TabsState => {
  const byId = new Map(state.order.map((e) => [e.tabId, e]));
  const order: Array<TabEntry> = newTabIds.map((id) => byId.get(id) ?? { tabId: id, agentId: null });
  let activeIndex = INVALID_ACTIVE_INDEX;
  if (state.activeIndex >= 0 && state.activeIndex < state.order.length) {
    const activeTabId = state.order[state.activeIndex].tabId;
    const newIdx = newTabIds.indexOf(activeTabId);
    if (newIdx !== -1) activeIndex = newIdx;
  }
  return { order, activeIndex };
};

/**
 * Workspace IDs the user has asked to close. Records the user's *intent*, not
 * the in-flight request — entries persist past the API ack so that:
 *   - Stale WebSocket snapshots arriving after the close (e.g. from a slower,
 *     earlier open PATCH whose response is reordered behind the close ack)
 *     can't revert the workspace back to open.
 *   - The "Closed" pill stays stable instead of flickering as out-of-order
 *     SUs land.
 *
 * `updateWorkspacesAtom` consults this set and forces incoming `isOpen=true`
 * snapshots to `false` for any workspace in here. Entries are cleared by:
 *   - `openWorkspaceTabAtom` (user expressed the opposite intent)
 *   - `optimisticDeleteWorkspaceAtom` (workspace going away entirely)
 *   - `.catch` on the close API call (the close never happened, undo intent)
 */
const pendingCloseWorkspaceIdsAtom = atom<ReadonlySet<string>>(new Set<string>());

/** Add `ids` to pendingCloseWorkspaceIdsAtom (idempotent). */
const markPendingCloseAtom = atom(null, (get, set, ids: ReadonlyArray<string>): void => {
  if (ids.length === 0) return;
  const current = get(pendingCloseWorkspaceIdsAtom);
  const next = new Set(current);
  let didAdd = false;
  for (const id of ids) {
    if (!next.has(id)) {
      next.add(id);
      didAdd = true;
    }
  }
  if (didAdd) set(pendingCloseWorkspaceIdsAtom, next);
});

/** Remove `ids` from pendingCloseWorkspaceIdsAtom (idempotent). */
const clearPendingCloseAtom = atom(null, (get, set, ids: ReadonlyArray<string>): void => {
  if (ids.length === 0) return;
  const current = get(pendingCloseWorkspaceIdsAtom);
  if (ids.every((id) => !current.has(id))) return;
  const next = new Set(current);
  for (const id of ids) next.delete(id);
  set(pendingCloseWorkspaceIdsAtom, next);
});

/**
 * Workspace IDs the user has asked to open. Symmetric to pendingClose: records
 * the user's *intent* so the tab appears immediately even when the workspace's
 * server-side `isOpen` is still `false`, and so a stale `isOpen=false` snapshot
 * can't undo the open. Cleared by `closeWorkspaceTabAtom` (opposite intent),
 * `optimisticDeleteWorkspaceAtom` (workspace going away), and `.catch` on the
 * open API call (the open never happened).
 */
const pendingOpenWorkspaceIdsAtom = atom<ReadonlySet<string>>(new Set<string>());

/** Add `ids` to pendingOpenWorkspaceIdsAtom (idempotent). */
const markPendingOpenAtom = atom(null, (get, set, ids: ReadonlyArray<string>): void => {
  if (ids.length === 0) return;
  const current = get(pendingOpenWorkspaceIdsAtom);
  const next = new Set(current);
  let didAdd = false;
  for (const id of ids) {
    if (!next.has(id)) {
      next.add(id);
      didAdd = true;
    }
  }
  if (didAdd) set(pendingOpenWorkspaceIdsAtom, next);
});

/** Remove `ids` from pendingOpenWorkspaceIdsAtom (idempotent). */
const clearPendingOpenAtom = atom(null, (get, set, ids: ReadonlyArray<string>): void => {
  if (ids.length === 0) return;
  const current = get(pendingOpenWorkspaceIdsAtom);
  if (ids.every((id) => !current.has(id))) return;
  const next = new Set(current);
  for (const id of ids) next.delete(id);
  set(pendingOpenWorkspaceIdsAtom, next);
});

/**
 * The effective set of open tab IDs: tabOrderAtom filtered to only include
 * IDs that are open workspaces or pseudo-tabs (closed/deleted workspaces
 * and workspaces unknown to this session are filtered out). IDs with a close
 * request in flight are also excluded to defeat stale-snapshot flicker.
 *
 * New workspaces are added to tabOrderAtom explicitly by updateWorkspacesAtom
 * (on WebSocket snapshot) and openWorkspaceTabAtom (user opens a workspace),
 * so we don't need to auto-append open workspaces that aren't in tabOrder.
 */
export const effectiveOpenTabIdsAtom = atom<Array<string>>((get) => {
  const tabOrder = get(tabOrderAtom);
  const openIds = new Set(get(openWorkspaceIdsAtom));
  const pendingClose = get(pendingCloseWorkspaceIdsAtom);
  const pendingOpen = get(pendingOpenWorkspaceIdsAtom);
  return tabOrder.filter(
    (id) => (openIds.has(id) || pendingOpen.has(id) || isPseudoTabId(id)) && !pendingClose.has(id),
  );
});

/**
 * Last pathname the user was on outside of /home. Drives the "toggle off"
 * half of the Home button: clicking Home while already on /home pops back
 * to this pathname so Home behaves like a peekable overlay rather than a
 * routed destination. Tracked in-memory only — fresh sessions start
 * empty and fall back to the router's default redirect.
 */
export const lastNonHomeLocationAtom = atom<string | null>(null);

/**
 * IDs of workspaces that exist but are closed (is_open=false on the backend),
 * plus any with a close request in flight. Including pending-close IDs makes
 * the ClosedWorkspacesPill appear instantly on close and stay stable through
 * any stale isOpen=true snapshot that arrives before the ack (SCU-455).
 */
export const closedWorkspaceIdsAtom = atom<Array<string>>((get) => {
  const workspaces = get(workspacesArrayAtom);
  if (workspaces === undefined) {
    return [];
  }
  const pendingClose = get(pendingCloseWorkspaceIdsAtom);
  const pendingOpen = get(pendingOpenWorkspaceIdsAtom);
  return workspaces
    .filter((ws) => !pendingOpen.has(ws.objectId) && (ws.isOpen === false || pendingClose.has(ws.objectId)))
    .map((ws) => ws.objectId);
});

/**
 * Close a workspace tab.
 * - For pseudo-tabs (Home, Settings, etc.): remove from tab order locally.
 * - For real workspace IDs: record the close intent in pendingClose so the tab
 *   hides immediately and stays hidden even if a stale `isOpen=true` snapshot
 *   arrives later. The intent persists until the user opens or deletes the
 *   workspace; on API failure we clear the intent and surface a retry toast.
 */
export const closeWorkspaceTabAtom = atom(null, (get, set, tabId: string): void => {
  if (isPseudoTabId(tabId)) {
    set(tabsAtom, applyClose(get(tabsAtom), tabId));
    return;
  }
  // Closing a real workspace tab is reversible — the entry stays in
  // tabsAtom.order so the tab can be re-opened later. activeIndex is
  // therefore intentionally NOT adjusted here; effectiveOpenTabIdsAtom
  // is the close-aware filter that hides the tab from the UI.
  // Closing supersedes any prior open intent.
  set(clearPendingOpenAtom, [tabId]);
  set(markPendingCloseAtom, [tabId]);
  // Free cached data for the closed tab; it refetches on re-open.
  removeWorkspaceQueriesCache(tabId);
  workspaceSetupStatusAtomFamily.remove(tabId);
  updateWorkspaceApi({ path: { workspace_id: tabId }, body: { isOpen: false } }).catch(() => {
    set(clearPendingCloseAtom, [tabId]);
    set(workspaceOpenCloseErrorToastAtom, {
      title: "Failed to close workspace",
      description: "Try again or check your connection.",
      type: ToastType.ERROR_PROMINENT,
      action: {
        label: "Retry",
        handleClick: (): void => {
          set(workspaceOpenCloseErrorToastAtom, null);
          set(closeWorkspaceTabAtom, tabId);
        },
      },
    });
  });
});

/**
 * Open a workspace as a tab: optimistically insert into the tab order and
 * call the backend. On failure, roll back the insert (if we were the ones
 * that added it) and surface a toast.
 */
export const openWorkspaceTabAtom = atom(null, (get, set, workspaceId: string): void => {
  // Opening overrides any prior close intent and records the new one so the
  // tab appears immediately even before the open ack lands.
  set(clearPendingCloseAtom, [workspaceId]);
  set(markPendingOpenAtom, [workspaceId]);
  const before = get(tabsAtom);
  const didInsert = !before.order.some((e) => e.tabId === workspaceId);
  if (didInsert) {
    set(tabsAtom, applyOpen(before, { tabId: workspaceId, agentId: null }, { setActive: false }));
  }
  updateWorkspaceApi({ path: { workspace_id: workspaceId }, body: { isOpen: true } }).catch(() => {
    set(clearPendingOpenAtom, [workspaceId]);
    if (didInsert) {
      set(tabsAtom, applyClose(get(tabsAtom), workspaceId));
    }
    set(workspaceOpenCloseErrorToastAtom, {
      title: "Failed to open workspace",
      description: "Try again or check your connection.",
      type: ToastType.ERROR_PROMINENT,
      action: {
        label: "Retry",
        handleClick: (): void => {
          set(workspaceOpenCloseErrorToastAtom, null);
          set(openWorkspaceTabAtom, workspaceId);
        },
      },
    });
  });
});

/** Close all workspace tabs via batch endpoint. */
export const closeAllWorkspaceTabsAtom = atom(null, (get, set): void => {
  const openIds = get(openWorkspaceIdsAtom);
  if (openIds.length === 0) return;
  set(clearPendingOpenAtom, openIds);
  set(markPendingCloseAtom, openIds);
  for (const id of openIds) {
    removeWorkspaceQueriesCache(id);
    workspaceSetupStatusAtomFamily.remove(id);
  }
  batchUpdateOpenState({ body: { workspaceIds: [...openIds], isOpen: false } }).catch(() => {
    set(clearPendingCloseAtom, openIds);
    set(workspaceOpenCloseErrorToastAtom, {
      title: "Failed to close workspaces",
      description: "Try again or check your connection.",
      type: ToastType.ERROR_PROMINENT,
      action: null,
    });
  });
});

/** Close all workspace tabs except the specified one. */
export const closeOtherWorkspaceTabsAtom = atom(null, (get, set, keepWorkspaceId: string): void => {
  const openIds = get(openWorkspaceIdsAtom);
  const toClose = openIds.filter((id) => id !== keepWorkspaceId);
  if (toClose.length === 0) return;
  set(clearPendingOpenAtom, toClose);
  set(markPendingCloseAtom, toClose);
  for (const id of toClose) {
    removeWorkspaceQueriesCache(id);
    workspaceSetupStatusAtomFamily.remove(id);
  }
  batchUpdateOpenState({ body: { workspaceIds: toClose, isOpen: false } }).catch(() => {
    set(clearPendingCloseAtom, toClose);
    set(workspaceOpenCloseErrorToastAtom, {
      title: "Failed to close workspaces",
      description: "Try again or check your connection.",
      type: ToastType.ERROR_PROMINENT,
      action: null,
    });
  });
});

export const updateWorkspacesAtom = atom(null, (get, set, workspaces: ReadonlyArray<Workspace>) => {
  const currentWorkspaceIds = new Set(get(workspaceIdsAtom) ?? []);
  const isHydrated = get(hasHydratedWorkspaceTabsAtom);
  const initialTabsState = get(tabsAtom);
  const pendingClose = get(pendingCloseWorkspaceIdsAtom);
  const pendingOpen = get(pendingOpenWorkspaceIdsAtom);
  let nextTabsState = initialTabsState;

  const newlyDeletedIds = new Set<string>();

  workspaces.forEach((incoming) => {
    if (incoming.isDeleted) {
      // Mirror task deletion pattern: remove from IDs and null out atom
      currentWorkspaceIds.delete(incoming.objectId);
      set(workspaceAtomFamily(incoming.objectId), null);
      newlyDeletedIds.add(incoming.objectId);
      nextTabsState = applyClose(nextTabsState, incoming.objectId);
      return;
    }

    // Honor the user's last close/open intent over potentially-stale snapshots.
    // Out-of-order PATCH responses (e.g. an earlier slow open landing after the
    // close ack) would otherwise revert the user's action.
    let workspace = incoming;
    if (pendingClose.has(incoming.objectId) && incoming.isOpen) {
      workspace = { ...workspace, isOpen: false };
    } else if (pendingOpen.has(incoming.objectId) && incoming.isOpen === false) {
      workspace = { ...workspace, isOpen: true };
    }

    // If the backend signalled a new diff (via `diffUpdatedAt`), invalidate
    // every cached git-derived query (diff/files/commits/fileContent) so
    // active observers refetch. The same `diffUpdatedAt` bump fires for any
    // git event the backend surfaces — file changes, commits, branch
    // movement — so it's the right shared trigger. Non-git workspace queries
    // (e.g. future MR status) live outside the `git` subtree and are
    // unaffected. We compare against the prior atom value here rather than
    // tracking the previous snapshot externally.
    const previous = get(workspaceAtomFamily(workspace.objectId));
    if (previous !== null && previous.diffUpdatedAt !== workspace.diffUpdatedAt) {
      invalidateWorkspaceGitQueries(workspace.objectId);
    }

    set(workspaceAtomFamily(workspace.objectId), workspace);
    const isNew = !currentWorkspaceIds.has(workspace.objectId);
    currentWorkspaceIds.add(workspace.objectId);

    // Seed the setup-status atom from the persisted Workspace fields when the
    // streaming layer hasn't already pushed a status (e.g. on app restart for
    // a terminal-state workspace). Live transitions from the runner overwrite
    // this via WorkspaceSetupStatus events. Persisted log content arrives as
    // a synthetic WorkspaceSetupOutputChunk in the same initial stream dump.
    if (workspace.setupStatus !== undefined && workspace.setupStatus !== null) {
      const existingStatus = get(workspaceSetupStatusAtomFamily(workspace.objectId));
      if (existingStatus === null) {
        set(workspaceSetupStatusAtomFamily(workspace.objectId), {
          workspaceId: workspace.objectId,
          status: workspace.setupStatus as "not_configured" | "pending" | "running" | "succeeded" | "failed" | "legacy",
          runId: workspace.setupRunId ?? null,
          exitCode: workspace.setupExitCode ?? null,
          startedAt: workspace.setupStartedAt ?? null,
          finishedAt: workspace.setupFinishedAt ?? null,
          logTruncated: workspace.setupLogTruncated ?? false,
        });
      }
    }

    // After hydration, add genuinely new open workspaces to the tab order.
    if (isHydrated && isNew && workspace.isOpen) {
      nextTabsState = applyOpen(nextTabsState, { tabId: workspace.objectId, agentId: null }, { setActive: false });
    }
  });

  set(workspaceIdsAtom, Array.from(currentWorkspaceIds));

  // Propagate stream-driven deletions to deletedWorkspaceIdsAtom so that
  // components with their own workspace lists (e.g. RecentWorkspaces) can
  // filter them out without relying solely on the optimistic delete path.
  if (newlyDeletedIds.size > 0) {
    const currentDeleted = get(deletedWorkspaceIdsAtom);
    const merged = new Set(currentDeleted);
    for (const id of newlyDeletedIds) {
      merged.add(id);
    }

    if (merged.size > currentDeleted.size) {
      set(deletedWorkspaceIdsAtom, merged);
    }
  }

  if (!isHydrated) {
    set(hasHydratedWorkspaceTabsAtom, true);

    // One-time migration: if the old localStorage key exists, migrate its
    // open/closed state to the backend and adopt its ordering for tabsAtom.
    const OLD_KEY = "sculptor-open-workspace-tab-ids";
    const oldRaw = localStorage.getItem(OLD_KEY);
    if (oldRaw !== null) {
      try {
        const oldOpenIds = JSON.parse(oldRaw) as Array<string>;
        const oldOpenSet = new Set(oldOpenIds);

        // Workspaces NOT in the old open set should be closed on the backend
        const toClose = Array.from(currentWorkspaceIds).filter((id) => !oldOpenSet.has(id) && !isPseudoTabId(id));
        console.info("[workspace-migration] migrating from localStorage to backend:", {
          openCount: oldOpenIds.filter((id) => !isPseudoTabId(id)).length,
          closeCount: toClose.length,
          totalWorkspaces: currentWorkspaceIds.size,
        });
        if (toClose.length > 0) {
          void batchUpdateOpenState({ body: { workspaceIds: toClose, isOpen: false } });
        }

        // Adopt the old tab order (it already includes pseudo-tabs)
        nextTabsState = {
          order: oldOpenIds.map((tabId): TabEntry => ({ tabId, agentId: null })),
          activeIndex: INVALID_ACTIVE_INDEX,
        };
      } catch (e) {
        console.warn("[workspace-migration] failed to parse old localStorage key:", e);
      }
      localStorage.removeItem(OLD_KEY);
    } else {
      const hasRealTabs = nextTabsState.order.some((e) => !isPseudoTabId(e.tabId));
      if (!hasRealTabs) {
        // No saved tab order (first-time or cleared localStorage) — initialize
        // tab order from all open workspaces, preserving any existing pseudo-tabs.
        const openIds = Array.from(currentWorkspaceIds).filter((id) => {
          const ws = get(workspaceAtomFamily(id));
          return ws !== null && !ws.isDeleted && ws.isOpen;
        });
        nextTabsState = {
          ...nextTabsState,
          order: [...nextTabsState.order, ...openIds.map((id): TabEntry => ({ tabId: id, agentId: null }))],
        };
      }
      // If saved tab order exists, leave it as-is; effectiveOpenTabIdsAtom
      // will filter out closed/deleted workspaces and append newly opened ones.
    }
  }

  if (nextTabsState !== initialTabsState) {
    set(tabsAtom, nextTabsState);
  }
});

export const optimisticDeleteWorkspaceAtom = atom(null, (get, set, workspaceId: string): Workspace | null => {
  const workspace = get(workspaceAtomFamily(workspaceId));
  if (workspace === null) {
    return null;
  }
  const snapshot = workspace;
  set(workspaceAtomFamily(workspaceId), null);
  // Keep workspaceId in workspaceIdsAtom so that a WebSocket snapshot
  // arriving before the server confirms deletion doesn't treat it as
  // a "new" workspace and auto-open it as a tab. workspacesArrayAtom
  // filters out null atoms, so it won't appear in the UI.
  // Remove from tab order so the tab disappears immediately
  set(tabsAtom, applyClose(get(tabsAtom), workspaceId));
  // Track the deletion so components with their own workspace lists
  // (e.g. RecentWorkspaces) can filter it out without a page reload.
  const deleted = new Set(get(deletedWorkspaceIdsAtom));
  deleted.add(workspaceId);
  set(deletedWorkspaceIdsAtom, deleted);
  // Free cached data for the deleted workspace.
  removeWorkspaceQueriesCache(workspaceId);
  workspaceSetupStatusAtomFamily.remove(workspaceId);
  // The workspace is going away — drop any lingering open/close intent.
  set(clearPendingCloseAtom, [workspaceId]);
  set(clearPendingOpenAtom, [workspaceId]);
  return snapshot;
});

export const rollbackDeleteWorkspaceAtom = atom(
  null,
  (get, set, { workspaceId, snapshot }: { workspaceId: string; snapshot: Workspace }): void => {
    set(workspaceAtomFamily(workspaceId), snapshot);
    // workspaceIdsAtom is not modified during optimistic delete, so no
    // need to re-add. Just restore the tab order entry.
    set(tabsAtom, applyOpen(get(tabsAtom), { tabId: workspaceId, agentId: null }, { setActive: false }));
  },
);

/** Per-workspace last-viewed agent ID, derived from `tabsAtom.order`. */
export const agentIdForWorkspaceAtomFamily = atomFamily<string, Atom<string | null>>((wsId) =>
  atom<string | null>((get) => get(tabsAtom).order.find((e) => e.tabId === wsId)?.agentId ?? null),
);

/**
 * Derived: workspace id → last-viewed agent id, sourced from `tabsAtom.order`.
 * Used by tab click handlers to navigate directly to the saved agent without
 * a one-by-one lookup against the atom family.
 */
export const agentIdsByWorkspaceAtom = atom<ReadonlyMap<string, string>>((get) => {
  const map = new Map<string, string>();
  for (const entry of get(tabsAtom).order) {
    if (entry.tabId.startsWith("ws_") && entry.agentId !== null) {
      map.set(entry.tabId, entry.agentId);
    }
  }
  return map;
});

/** Move the activeIndex pointer to the entry with the given tabId (no-op if absent). */
export const setActiveTabByIdAtom = atom(null, (get, set, tabId: string): void => {
  set(tabsAtom, applySetActive(get(tabsAtom), tabId));
});

/** Set the last-viewed agent ID on the entry for the given workspace. */
export const setAgentForWorkspaceAtom = atom(
  null,
  (get, set, { wsId, agentId }: { wsId: string; agentId: string | null }): void => {
    set(tabsAtom, applySetAgent(get(tabsAtom), wsId, agentId));
  },
);

/** Append a pseudo-tab to the tab order if it isn't already present. */
export const ensurePseudoTabAtom = atom(null, (get, set, tabId: string): void => {
  set(tabsAtom, applyOpen(get(tabsAtom), { tabId, agentId: null }, { setActive: false }));
});

/** Replace the entire tab list with a single entry, preserving its existing agentId. */
export const keepOnlyTabAtom = atom(null, (get, set, tabId: string): void => {
  const current = get(tabsAtom);
  const existing = current.order.find((e) => e.tabId === tabId);
  set(tabsAtom, {
    order: [{ tabId, agentId: existing?.agentId ?? null }],
    activeIndex: 0,
  });
});

/** Clear all tabs and reset activeIndex to its sentinel. */
export const clearAllTabsAtom = atom(null, (_get, set): void => {
  set(tabsAtom, { order: [], activeIndex: INVALID_ACTIVE_INDEX });
});

/** Reorder tabs to match `newTabIds`, preserving each entry's agentId and active selection. */
export const reorderTabsAtom = atom(null, (get, set, newTabIds: Array<string>): void => {
  set(tabsAtom, applyReorder(get(tabsAtom), newTabIds));
});

/**
 * Splice the entry for `tabId` out of `tabsAtom.order`. Use this when you
 * want the tab gone for good (e.g. the underlying workspace was deleted),
 * not for the reversible close-intent flow handled by `closeWorkspaceTabAtom`.
 */
export const removeTabFromOrderAtom = atom(null, (get, set, tabId: string): void => {
  set(tabsAtom, applyClose(get(tabsAtom), tabId));
});
