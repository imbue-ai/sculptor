// Idle garbage collection for orphaned per-workspace layout snapshots.
//
// A workspace deleted through the app removes its `sculptor-layout-ws-<id>` key
// via `removeWorkspaceLayoutAtom`, but deletions that never run in this client
// (another device, a backend-side removal, a crash mid-delete) leave the key
// behind forever. This sweep prunes those leftovers once per session, after the
// workspace list has loaded, during browser idle time.
//
// Deliberately conservative:
//   - runs at most once per session, and only once the workspace list is loaded
//     (an undefined list means "still loading", never "no workspaces");
//   - considers only keys with the exact per-workspace layout prefix — every
//     other localStorage key is untouched;
//   - a pruned key costs at worst one workspace's layout arrangement, never data.

import { useStore } from "jotai";
import { useEffect } from "react";

import { workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";

import { WORKSPACE_KEY_PREFIX } from "./LocalStorageLayoutAdapter.ts";

// Fallback delay when requestIdleCallback is unavailable: late enough to stay
// clear of the initial-load work the idle callback is meant to avoid.
const IDLE_FALLBACK_DELAY_MS = 3000;

const scheduleWhenIdle = (task: () => void): void => {
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(() => task());
  } else {
    setTimeout(task, IDLE_FALLBACK_DELAY_MS);
  }
};

/**
 * The subset of `storedKeys` that are per-workspace layout snapshots whose
 * workspace id is not in `liveWorkspaceIds`. Pure so the pruning decision is
 * unit-testable without touching localStorage.
 */
export function findOrphanedWorkspaceLayoutKeys(
  storedKeys: ReadonlyArray<string>,
  liveWorkspaceIds: ReadonlySet<string>,
): Array<string> {
  return storedKeys.filter(
    (key) => key.startsWith(WORKSPACE_KEY_PREFIX) && !liveWorkspaceIds.has(key.slice(WORKSPACE_KEY_PREFIX.length)),
  );
}

/** Remove every orphaned per-workspace layout key from localStorage. */
export function pruneOrphanedWorkspaceLayouts(liveWorkspaceIds: ReadonlySet<string>): void {
  let storedKeys: Array<string>;
  try {
    storedKeys = Object.keys(localStorage);
  } catch {
    // Missing/blocked localStorage: nothing to sweep.
    return;
  }

  for (const key of findOrphanedWorkspaceLayoutKeys(storedKeys, liveWorkspaceIds)) {
    try {
      localStorage.removeItem(key);
    } catch {
      // Ignore: a failed removal just leaves the orphan for a later session.
    }
  }
}

let hasSweptThisSession = false;

/**
 * Arms the once-per-session sweep. Waits (without subscribing the caller to
 * re-renders) for the workspace list to finish loading, then prunes during
 * idle time. Mounted by the workspace shell; safe to mount many times.
 */
export function useOrphanedLayoutGc(): void {
  const store = useStore();

  useEffect(() => {
    if (hasSweptThisSession) {
      return;
    }

    // Arm once the list has loaded, but prune against the ids read at idle time,
    // not a load-time snapshot: a workspace created (and its layout key seeded)
    // between load and the idle callback must not have its key swept as orphaned.
    const trySweep = (): boolean => {
      const workspaceIds = store.get(workspaceIdsAtom);
      if (workspaceIds === undefined || hasSweptThisSession) {
        return false;
      }
      hasSweptThisSession = true;
      scheduleWhenIdle(() => {
        const liveIds = store.get(workspaceIdsAtom);
        if (liveIds !== undefined) {
          pruneOrphanedWorkspaceLayouts(new Set(liveIds));
        }
      });
      return true;
    };

    if (trySweep()) {
      return;
    }
    const unsubscribe = store.sub(workspaceIdsAtom, () => {
      if (trySweep()) {
        unsubscribe();
      }
    });
    return unsubscribe;
  }, [store]);
}
