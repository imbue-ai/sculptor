import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { NewBranchNameValidationResponse, WorkspaceInitializationStrategy } from "~/api";
import { previewBranchName, validateNewBranchName, WorkspaceInitializationStrategy as Strategy } from "~/api";
import type { BackendQueryKeyResult } from "~/common/queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/queryClient.ts";

/**
 * Status of the displayed branch name, from the debounced backend check:
 * - `unknown`: not checked yet (empty name, in-place mode, or in flight)
 * - `invalid`: not a legal git ref name
 * - `exists`: legal, but already a branch in the repo
 * - `available`: legal and free to use
 */
export type BranchNameStatus = "unknown" | "invalid" | "exists" | "available";

type BranchNamePreviewState = {
  /** The auto-filled value sourced from the backend `preview-branch-name` endpoint. */
  preview: string;
  /** The value the user actually sees: `override` if set, otherwise `preview`. */
  displayedValue: string;
  /** True while the auto preview isn't settled yet (debounce gap or fetch in flight). */
  isLoading: boolean;
  /** Result of the debounced `validate-new-branch-name` check on `displayedValue`. */
  status: BranchNameStatus;
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
const VALIDATION_DEBOUNCE_MS = 300;

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

const validateNewBranchNameQueryKey = (projectId: string | null, name: string): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "project", projectId, "validateNewBranchName", name] as const,
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

// Returns null (rather than a verdict) when the backend gave no answer, so the
// caller can distinguish "not checked" from a real validation result.
const fetchBranchNameValidation = async (
  projectId: string,
  name: string,
  signal: AbortSignal,
): Promise<NewBranchNameValidationResponse | null> => {
  const { data } = await validateNewBranchName({
    path: { project_id: projectId },
    query: { name },
    meta: { signal },
  });
  return data ?? null;
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

  // Debounce the displayed value before the validation check so it fires on the
  // settled name, not on every intermediate keystroke or preview update.
  const debouncedBranchName = useDebouncedValue(displayedValue.trim(), VALIDATION_DEBOUNCE_MS);
  const validationKey = validateNewBranchNameQueryKey(projectId, debouncedBranchName);
  const isValidationEnabled = validationKey.isValid && mode !== Strategy.IN_PLACE && debouncedBranchName !== "";
  const validationQuery = useQuery({
    queryKey: validationKey.key,
    queryFn: ({ signal }) => fetchBranchNameValidation(projectId!, debouncedBranchName, signal),
    enabled: isValidationEnabled,
    placeholderData: keepPreviousData,
    retry: false,
  });

  // "unknown" whenever the check is disabled or unanswered, so a stale verdict
  // never lingers once the name empties or the mode stops needing a new branch.
  let status: BranchNameStatus = "unknown";
  if (isValidationEnabled && !validationQuery.isError && validationQuery.data != null) {
    const { isValid, alreadyExists: doesBranchExist } = validationQuery.data;
    status = !isValid ? "invalid" : doesBranchExist ? "exists" : "available";
  }

  return { preview, displayedValue, isLoading, status };
}
