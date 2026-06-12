import { useAtomValue, useStore } from "jotai";
import { useCallback, useEffect, useState } from "react";

import type { RepoInfo } from "../../../api";
import { getCurrentBranch, getRepoInfo } from "../../../api";
import type { ProjectID } from "../../Types";
import { repoInfoAtomFamily } from "../atoms/repoInfo.ts";

const RETRY_INTERVAL_MS = 3_000;
const MAX_RETRIES = 10;

type RepoInfoHookReturn = {
  /** Current repository information for this project */
  repoInfo: RepoInfo | null;
  /** Function to refetch repository information from the server */
  fetchRepoInfo: () => Promise<RepoInfo | undefined>;
  /** Function to fetch just the current branch */
  fetchCurrentBranch: () => Promise<void>;
};

export const useRepoInfo = (projectId: ProjectID): RepoInfoHookReturn => {
  const store = useStore();
  const repoInfo = useAtomValue(repoInfoAtomFamily(projectId));
  const [retryAttempt, setRetryAttempt] = useState(0);

  const fetchRepoInfo = useCallback(async (): Promise<RepoInfo | undefined> => {
    try {
      const { data: repoInfo } = await getRepoInfo({
        path: { project_id: projectId },
        meta: { skipWsAck: true },
      });

      // Update the atom for this project
      const repoInfoAtom = repoInfoAtomFamily(projectId);
      store.set(repoInfoAtom, repoInfo);

      return repoInfo;
    } catch (error) {
      console.error(`Failed to load repo info for project ${projectId}:`, error);
      // Clear the atom so the retry effect fires even when stale data existed
      // from a previous successful fetch.
      const repoInfoAtom = repoInfoAtomFamily(projectId);
      store.set(repoInfoAtom, null);
    }
  }, [projectId, store]);

  const fetchCurrentBranch = useCallback(async (): Promise<void> => {
    try {
      const { data: currentBranchInfo } = await getCurrentBranch({
        path: { project_id: projectId },
        meta: { skipWsAck: true },
      });

      const repoInfoAtom = repoInfoAtomFamily(projectId);
      const existingRepoInfo = store.get(repoInfoAtom);

      // Only update when we already have full repo info from a successful
      // fetchRepoInfo call.  If existingRepoInfo is null (e.g. because
      // fetchRepoInfo failed with a transient error), writing a partial
      // RepoInfo with empty recentBranches would permanently disable the
      // "Create Workspace" button AND prevent the retry effect from firing
      // (since it only retries when repoInfo is null).
      //
      // Recovery is driven by fetchRepoInfo's retry loop (see the useEffect
      // below): once fetchRepoInfo succeeds it populates the full atom,
      // and subsequent fetchCurrentBranch calls will see non-null data.
      if (existingRepoInfo === null) {
        return;
      }

      const newRepoInfo: RepoInfo = {
        currentBranch: currentBranchInfo.currentBranch,
        projectId: projectId,
        recentBranches: existingRepoInfo.recentBranches,
        repoPath: existingRepoInfo.repoPath,
      };

      store.set(repoInfoAtom, newRepoInfo);
    } catch (error) {
      console.error(`Failed to load current branch for project ${projectId}:`, error);
    }
  }, [projectId, store]);

  // Retry fetching repo info if the initial fetch failed and left the atom
  // null.  This handles transient backend errors (e.g. the repo directory
  // being temporarily unavailable) that would otherwise leave the UI stuck
  // in a permanent "Loading repository info..." state.
  //
  // retryAttempt is state (not a ref) so each failed retry re-fires this
  // effect to schedule the next attempt.  Without that, when the atom is
  // already null and a retry's catch block calls store.set(null), Jotai
  // short-circuits the no-op write — no re-render, no effect re-run, and
  // retries silently stop after the first attempt.
  useEffect(() => {
    if (repoInfo !== null) {
      if (retryAttempt !== 0) {
        setRetryAttempt(0);
      }
      return;
    }

    if (retryAttempt >= MAX_RETRIES) {
      return;
    }

    const timer = setTimeout(() => {
      setRetryAttempt((prev) => prev + 1);
      fetchRepoInfo();
    }, RETRY_INTERVAL_MS);

    return (): void => clearTimeout(timer);
  }, [repoInfo, fetchRepoInfo, retryAttempt]);

  return {
    repoInfo,
    fetchRepoInfo,
    fetchCurrentBranch,
  };
};
