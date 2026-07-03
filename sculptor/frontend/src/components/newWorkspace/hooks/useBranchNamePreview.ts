import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { branchExists, previewBranchName, WorkspaceInitializationStrategy as Strategy } from "~/api";
import type { BackendQueryKeyResult } from "~/common/queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/queryClient.ts";

export type BranchNameCollisionState = "unknown" | "exists" | "available";

type BranchNamePreviewState = {
  /** The auto-filled value sourced from the backend `preview-branch-name` endpoint. */
  preview: string;
  /** The value the user actually sees: `override` if set, otherwise `preview`. */
  displayedValue: string;
  /** True while the auto preview isn't settled yet (debounce gap or fetch in flight). */
  isLoading: boolean;
  /** Result of the debounced `branch-exists` check on `displayedValue`. */
  collision: BranchNameCollisionState;
};

type UseBranchNamePreviewArgs = {
  projectId: string | null;
  workspaceName: string;
  mode: WorkspaceInitializationStrategy;
  /** The user's manual override; null means "use the auto-filled preview". */
  override: string | null;
  /**
   * Bump to force a fresh preview fetch even when the other inputs are
   * unchanged. The "shuffle" button uses this to re-roll the random slug the
   * backend generates when the workspace name is blank. Defaults to 0.
   */
  shuffleNonce?: number;
};

const PREVIEW_DEBOUNCE_MS = 250;
const COLLISION_DEBOUNCE_MS = 300;

// Both endpoints are project-scoped and have no WebSocket push signal, so they
// key under the project namespace. The blank-workspace-name preview returns a
// random slug, so `shuffleNonce` is part of the key — an explicit shuffle lands
// on a fresh cache entry (and thus a fresh slug) rather than the cached one.
const branchNamePreviewQueryKey = (
  projectId: string | null,
  workspaceName: string,
  mode: WorkspaceInitializationStrategy,
  shuffleNonce: number,
): BackendQueryKeyResult => ({
  key: [
    SCULPTOR_QUERY_KEY_PREFIX,
    "project",
    projectId,
    "branchNamePreview",
    mode,
    workspaceName,
    shuffleNonce,
  ] as const,
  isValid: projectId !== null,
});

const branchExistsQueryKey = (projectId: string | null, name: string): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "project", projectId, "branchExists", name] as const,
  isValid: projectId !== null,
});

const fetchBranchNamePreview = async (
  projectId: string,
  workspaceName: string,
  mode: WorkspaceInitializationStrategy,
  signal: AbortSignal,
): Promise<string> => {
  const { data } = await previewBranchName({
    query: { project_id: projectId, workspace_name: workspaceName, mode },
    meta: { signal },
  });
  return data?.branchName ?? "";
};

// Returns null (rather than false) when the backend gave no answer, so the
// caller can distinguish "not checked" from a real "does not exist".
const fetchBranchExists = async (projectId: string, name: string, signal: AbortSignal): Promise<boolean | null> => {
  const { data } = await branchExists({
    path: { project_id: projectId },
    query: { name },
    meta: { signal },
  });
  return data ? data.exists : null;
};

// Delay a rapidly-changing value so it only settles after `delayMs` of quiet,
// keeping intermediate keystrokes out of a query key until the user pauses.
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return (): void => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function useBranchNamePreview({
  projectId,
  workspaceName,
  mode,
  override,
  shuffleNonce = 0,
}: UseBranchNamePreviewArgs): BranchNamePreviewState {
  const isManuallyEdited = override !== null;

  // Debounce the typed workspace name so each keystroke doesn't spawn a preview
  // request; discrete inputs (mode, shuffle) change the key immediately.
  const debouncedWorkspaceName = useDebouncedValue(workspaceName, PREVIEW_DEBOUNCE_MS);
  const previewKey = branchNamePreviewQueryKey(projectId, debouncedWorkspaceName, mode, shuffleNonce);
  const isPreviewEnabled = previewKey.isValid && mode !== Strategy.IN_PLACE && !isManuallyEdited;
  const previewQuery = useQuery({
    queryKey: previewKey.key,
    queryFn: ({ signal }) => fetchBranchNamePreview(projectId!, debouncedWorkspaceName, mode, signal),
    enabled: isPreviewEnabled,
    // Keep the last slug on screen while a fresh one loads instead of flashing empty.
    placeholderData: keepPreviousData,
    retry: false,
  });

  const preview = previewQuery.data ?? "";
  const displayedValue = override ?? preview;

  // `isLoading` covers the whole "auto value isn't settled" window: the debounce
  // gap before the request starts, plus the request itself.
  const isLoading = isPreviewEnabled && (previewQuery.isFetching || debouncedWorkspaceName !== workspaceName);

  // Debounce the displayed value before the existence check so it fires on the
  // settled name, not on every intermediate keystroke or preview update.
  const debouncedBranchName = useDebouncedValue(displayedValue.trim(), COLLISION_DEBOUNCE_MS);
  const collisionKey = branchExistsQueryKey(projectId, debouncedBranchName);
  const isCollisionEnabled = collisionKey.isValid && mode !== Strategy.IN_PLACE && debouncedBranchName !== "";
  const collisionQuery = useQuery({
    queryKey: collisionKey.key,
    queryFn: ({ signal }) => fetchBranchExists(projectId!, debouncedBranchName, signal),
    enabled: isCollisionEnabled,
    placeholderData: keepPreviousData,
    retry: false,
  });

  let collision: BranchNameCollisionState = "unknown";
  if (isCollisionEnabled && !collisionQuery.isError && collisionQuery.data != null) {
    collision = collisionQuery.data ? "exists" : "available";
  }

  return { preview, displayedValue, isLoading, collision };
}
