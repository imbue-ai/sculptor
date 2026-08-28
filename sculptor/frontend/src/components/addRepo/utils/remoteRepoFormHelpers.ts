// Pure helpers extracted from RemoteRepoForm so the .tsx file can keep its
// component-only exports (Fast Refresh requires component files to export
// only components; mixing helpers + components breaks HMR per
// react-refresh/only-export-components).
import type { DependenciesStatus, DependencyInfo } from "~/api";

import type { RemoteRepo } from "../RemoteRepoCombobox.tsx";
import type { RemoteCloneSubmit, RemoteRepoFormView } from "../RemoteRepoForm.tsx";
import type { RemoteProvider } from "../SourceRadioCards.tsx";

// Single source of truth for stripping a trailing `.git` from a repo URL or
// slug. Shared so RemoteRepoForm and useAddRepo don't each carry a copy.
export const stripGitSuffix = (name: string): string => (name.endsWith(".git") ? name.slice(0, -4) : name);

// The dependency status row that backs the remote-repo flow. GitHub is the only
// supported provider, so this reads `status.gh`.
export const getRemoteCliDependencyInfo = (status: DependenciesStatus | null): DependencyInfo | undefined => {
  if (!status) return undefined;
  return status.gh;
};

// Whether the remote form should show the "CLI not configured" section instead
// of the repo picker. Shared by RemoteRepoForm (which renders the section) and
// AddRepoDialog (which swaps the footer submit button for a "Configure …" CTA)
// so the two can never drift out of sync.
export const isRemoteFormShowingNotConfigured = (
  status: DependenciesStatus | null,
  view: RemoteRepoFormView,
  isRefreshing: boolean,
): boolean => {
  if (view !== "search") return false;
  const info = getRemoteCliDependencyInfo(status);
  // `isAuthenticated === null` means the auth probe timed out / couldn't tell.
  // The backend clone route treats that as usable (it only blocks on `false`),
  // so mirror that here: only `installed === false` or `isAuthenticated === false`
  // count as not-configured — never an unknown (`null`) auth state.
  const isConfigured = info?.installed === true && info.isAuthenticated !== false;
  // Suppress the not-configured branch until the first poll resolves; otherwise
  // a dialog opened without a pre-populated atom flashes it before the real
  // status arrives.
  const isWaitingForFirstStatus = isRefreshing && !info;
  return !isConfigured && !isWaitingForFirstStatus;
};

export const deriveNameFromUrl = (url: string): string => {
  const trimmed = url.trim();
  if (!trimmed) return "";
  // Handle both https://host/owner/repo(.git) and git@host:owner/repo(.git)
  const lastSlash = trimmed.lastIndexOf("/");
  const lastColon = trimmed.lastIndexOf(":");
  const cut = Math.max(lastSlash, lastColon);
  const tail = cut >= 0 ? trimmed.slice(cut + 1) : trimmed;
  return stripGitSuffix(tail);
};

export type SubmittableInputs = {
  provider: RemoteProvider;
  view: RemoteRepoFormView;
  selectedRepo: RemoteRepo | undefined;
  urlInput: string;
  name: string;
  effectiveTargetDir: string;
};

export const computeSubmittable = (inputs: SubmittableInputs): { ready: boolean; payload?: RemoteCloneSubmit } => {
  const { provider, view, selectedRepo, urlInput, name, effectiveTargetDir } = inputs;
  const effectiveUrl = view === "search" ? (selectedRepo?.cloneUrl ?? "") : urlInput.trim();
  const trimmedName = name.trim();
  const trimmedTargetDir = effectiveTargetDir.trim();
  if (!effectiveUrl || !trimmedName || !trimmedTargetDir) {
    return { ready: false };
  }
  return {
    ready: true,
    payload: {
      provider,
      url: effectiveUrl,
      targetDir: effectiveTargetDir,
      name: trimmedName,
      fullName: view === "search" ? selectedRepo?.fullName : undefined,
    },
  };
};
