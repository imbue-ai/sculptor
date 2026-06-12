import { atom, useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import { DiffStatus } from "../../../api";
import { parseDiff } from "../../../components/DiffUtils.ts";
import { activeWorkspaceIdAtom } from "../../../components/panels/atoms.ts";
import { determineFileStatus } from "../../../pages/workspace/panels/fileBrowser/utils.ts";
import { effectiveOpenTabIdsAtom, workspaceAtomFamily } from "../atoms/workspaces.ts";
import { prefetchWorkspaceCommits } from "./useWorkspaceCommits.ts";
import { ensureWorkspaceDiff, prefetchWorkspaceDiff } from "./useWorkspaceDiff.ts";
import { prefetchWorkspaceFileContent } from "./useWorkspaceFileContent.ts";
import { ensureWorkspaceFiles } from "./useWorkspaceFiles.ts";

// Wait for the active workspace's own queries to fire first — prefetching is
// a background warmth concern and must not contend with the visible page.
const PREFETCH_DELAY_MS = 3000;

// Cap on how many changed files get their contents warmed per workspace. The
// diff panel shows one file at a time; warming the first few covers the
// common "switch and look at the top change" path without flooding the
// backend for huge changesets.
const PREFETCH_FILE_CONTENT_LIMIT = 8;

/**
 * Warm the contents of a workspace's changed files so the diff panel's hunk
 * expansion data (old + new full file) is already local when a diff mounts.
 * Without this, the diff renders twice: once without expansion data, then
 * again (a full re-render of the diff web component) when the contents land.
 *
 * Uses the uncommitted diff's file list — the Changes panel's default scope.
 * The old side is fetched at HEAD to mirror `useFileLines` for uncommitted
 * diffs.
 */
const prefetchChangedFileContents = async (workspaceId: string, targetBranch: string | null): Promise<void> => {
  const diff = await ensureWorkspaceDiff(workspaceId, targetBranch);
  const uncommittedDiff = diff?.uncommittedDiff;
  if (!uncommittedDiff) return;
  const { fileChanges } = parseDiff(uncommittedDiff);
  for (const fileChange of fileChanges.slice(0, PREFETCH_FILE_CONTENT_LIMIT)) {
    const status = determineFileStatus(fileChange);
    const { previousFileName, newFileName, referenceFileName } = fileChange.fileNames;
    const filePath = newFileName ?? referenceFileName;
    if (status !== "D" && filePath) {
      void prefetchWorkspaceFileContent(workspaceId, filePath, null);
    }
    const oldPath = previousFileName ?? filePath;
    if (status !== "A" && oldPath) {
      void prefetchWorkspaceFileContent(workspaceId, oldPath, "HEAD");
    }
  }
};

/**
 * Warm a workspace's core git-derived caches (files, commits, diff, changed
 * files' contents) so switching to its tab renders from cache instead of
 * fetching on click. No-ops for ids without workspace data (e.g. pseudo-tabs)
 * and for anything already cached fresh (`prefetchQuery` respects staleTime).
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
    void prefetchChangedFileContents(workspaceId, targetBranch);
  }
});

// One entry per open tab: the workspace's diffUpdatedAt stamp. When a stamp
// changes (the agent committed / edited files), that workspace's git caches
// were just invalidated — so background workspaces go cold again unless
// re-warmed. Joining into a single string keeps the subscription cheap.
const openTabsDiffStampAtom = atom<string>((get) => {
  return get(effectiveOpenTabIdsAtom)
    .map((id) => `${id}=${get(workspaceAtomFamily(id))?.diffUpdatedAt ?? ""}`)
    .join("|");
});

/**
 * Keep every open workspace tab's data warm: prefetch when a tab first
 * becomes known (initial websocket hydration, tabs opened later) and
 * RE-prefetch when its `diffUpdatedAt` changes — each change invalidates the
 * workspace's git caches, and without a re-warm, switching to a workspace
 * whose agent has been working always pays the fetches on click.
 *
 * The active workspace is skipped: its mounted observers refetch themselves
 * on invalidation. Re-warms are debounced per change batch via the same
 * delay used for the initial warm-up.
 */
export const usePrefetchOpenWorkspaces = (): void => {
  const openTabsDiffStamp = useAtomValue(openTabsDiffStampAtom);
  const activeWorkspaceId = useAtomValue(activeWorkspaceIdAtom);
  const prefetchWorkspaceData = useSetAtom(prefetchWorkspaceDataAtom);
  const prefetchedStampsRef = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    const stampById = new Map<string, string>(
      openTabsDiffStamp
        .split("|")
        .filter(Boolean)
        .map((entry) => {
          const [id, stamp] = entry.split("=");
          return [id, stamp] as const;
        }),
    );
    const pendingIds = [...stampById.entries()]
      .filter(([id, stamp]) => id !== activeWorkspaceId && prefetchedStampsRef.current.get(id) !== stamp)
      .map(([id]) => id);
    if (pendingIds.length === 0) return;

    const timeout = setTimeout(() => {
      for (const id of pendingIds) {
        prefetchedStampsRef.current.set(id, stampById.get(id) ?? "");
        prefetchWorkspaceData(id);
      }
    }, PREFETCH_DELAY_MS);
    return (): void => clearTimeout(timeout);
  }, [openTabsDiffStamp, activeWorkspaceId, prefetchWorkspaceData]);
};
