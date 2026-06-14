// Pure helpers extracted from RemoteRepoForm so the .tsx file can keep its
// component-only exports (Fast Refresh requires component files to export
// only components; mixing helpers + components breaks HMR per
// react-refresh/only-export-components).
import type { RemoteRepo } from "./RemoteRepoCombobox.tsx";
import type { RemoteCloneSubmit, RemoteRepoFormView } from "./RemoteRepoForm.tsx";
import type { RemoteProvider } from "./SourceRadioCards.tsx";

const stripGitSuffix = (name: string): string => (name.endsWith(".git") ? name.slice(0, -4) : name);

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
