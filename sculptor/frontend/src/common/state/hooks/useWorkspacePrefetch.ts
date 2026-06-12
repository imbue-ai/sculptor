import { atom, useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import { DiffStatus } from "../../../api";
import { effectiveOpenTabIdsAtom, workspaceAtomFamily } from "../atoms/workspaces.ts";
import { prefetchWorkspaceCommits } from "./useWorkspaceCommits.ts";
import { prefetchWorkspaceDiff } from "./useWorkspaceDiff.ts";
import { ensureWorkspaceFiles } from "./useWorkspaceFiles.ts";

// Wait for the active workspace's own queries to fire first — prefetching is
// a background warmth concern and must not contend with the visible page.
const PREFETCH_DELAY_MS = 3000;

/**
 * Warm a workspace's core git-derived caches (files, commits, diff) so
 * switching to its tab renders from cache instead of fetching on click.
 * No-ops for ids without workspace data (e.g. pseudo-tabs) and for anything
 * already cached fresh (`prefetchQuery` respects staleTime).
 */
export const prefetchWorkspaceDataAtom = atom(null, (get, _set, workspaceId: string): void => {
  const workspace = get(workspaceAtomFamily(workspaceId));
  if (workspace === null || workspace.isDeleted) return;
  const targetBranch = workspace.targetBranch ?? null;
  void ensureWorkspaceFiles(workspaceId);
  void prefetchWorkspaceCommits(workspaceId, targetBranch);
  // The diff endpoint answers from the backend's cache only when the diff is
  // READY; while GENERATING the hook keeps its query disabled, so mirror that.
  if (workspace.diffStatus === DiffStatus.READY) {
    void prefetchWorkspaceDiff(workspaceId, targetBranch);
  }
});

/**
 * Prefetch every open workspace tab's data once it becomes known (initial
 * websocket hydration, plus tabs opened later), so tab switches hit warm
 * caches. Mounted once in PageLayout.
 */
export const usePrefetchOpenWorkspaces = (): void => {
  const openTabIds = useAtomValue(effectiveOpenTabIdsAtom);
  const prefetchWorkspaceData = useSetAtom(prefetchWorkspaceDataAtom);
  const prefetchedIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const pendingIds = openTabIds.filter((id) => !prefetchedIdsRef.current.has(id));
    if (pendingIds.length === 0) return;
    const timeout = setTimeout(() => {
      for (const id of pendingIds) {
        prefetchedIdsRef.current.add(id);
        prefetchWorkspaceData(id);
      }
    }, PREFETCH_DELAY_MS);
    return (): void => clearTimeout(timeout);
  }, [openTabIds, prefetchWorkspaceData]);
};
