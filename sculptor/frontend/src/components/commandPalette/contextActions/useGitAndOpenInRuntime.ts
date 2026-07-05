import { useStore } from "jotai/react";
import { useMemo } from "react";

import type { ExternalApp, Workspace } from "../../../api";
import { WorkspaceInitializationStrategy } from "../../../api";
import { openPathInExternalApp } from "../../../common/openInApp/items.tsx";
import { getBackendCapabilities } from "../../../common/state/atoms/backendCapabilities.ts";
import { chatActionsAtom } from "../../../common/state/atoms/chatActions.ts";
import { prStatusAtomFamily } from "../../../common/state/atoms/prStatus.ts";
import { repoInfoAtomFamily } from "../../../common/state/atoms/repoInfo.ts";
import { commitPromptAtom, prCreationPromptAtom } from "../../../common/state/atoms/userConfig.ts";
import { getCachedWorkspaceDiff } from "../../../common/state/hooks/useWorkspaceDiff.ts";
import { isMac } from "../../../electron/platform.ts";

/**
 * Slice of `WorkspaceActionRuntime` covering the git / external-app
 * actions added in the Cmd+K + right-click expansion. Lives in its own
 * hook because both consumers (WorkspaceSidebar and CommandRegistrations)
 * build their own runtime objects with different rename/delete handlers,
 * but share these atom-driven methods verbatim.
 */
export type GitAndOpenInRuntime = {
  commitChanges: (workspace: Workspace) => void;
  createMergeRequest: (workspace: Workspace) => void;
  openMergeRequest: (workspace: Workspace) => void;
  openInApp: (workspace: Workspace, app: ExternalApp) => void;

  hasUncommittedChanges: (workspace: Workspace) => boolean;
  hasOpenPr: (workspace: Workspace) => boolean;
  canCreatePr: (workspace: Workspace) => boolean;
  canOpenInOS: () => boolean;
  isMacUi: () => boolean;
};

/**
 * Resolves the local filesystem path the workspace's "Open in..." actions
 * should target. Mirrors RepoSegment's logic: in-place workspaces use the
 * source path; cloned workspaces use the environment's `code/` subdir
 * when an environment is set, falling back to source.
 */
const resolveOpenInPath = (workspace: Workspace, repoPath: string | null): string | null => {
  if (repoPath == null) return null;
  const isInPlace = workspace.initializationStrategy === WorkspaceInitializationStrategy.IN_PLACE;
  if (isInPlace) return repoPath;
  const codePath = workspace.environmentId ? `${workspace.environmentId}/code` : null;
  return codePath ?? repoPath;
};

export const useGitAndOpenInRuntime = (): GitAndOpenInRuntime => {
  const store = useStore();

  return useMemo<GitAndOpenInRuntime>(
    () => ({
      commitChanges: (_ws): void => {
        const chatActions = store.get(chatActionsAtom);
        const prompt = store.get(commitPromptAtom);
        // sendMessage is null when no agent is mounted; the descriptor's
        // `disabled` predicate already returns false in that case (no
        // diff visible), so this path is unreachable from the UI.
        void chatActions.sendMessage?.(prompt);
      },
      createMergeRequest: (ws): void => {
        const chatActions = store.get(chatActionsAtom);
        const prompt = store.get(prCreationPromptAtom);
        const targetBranch = ws.targetBranch;
        const message = targetBranch ? `${prompt}\n\nTarget the pull request against \`${targetBranch}\`.` : prompt;
        void chatActions.sendMessage?.(message);
      },
      openMergeRequest: (ws): void => {
        const prStatus = store.get(prStatusAtomFamily(ws.objectId));
        const url = prStatus?.prWebUrl;
        if (url) window.open(url, "_blank");
      },
      openInApp: (ws, app): void => {
        const repoInfo = store.get(repoInfoAtomFamily(ws.projectId));
        const path = resolveOpenInPath(ws, repoInfo?.repoPath ?? null);
        if (path == null) return;
        // Fire-and-forget. RepoSegment shows a per-instance AlertDialog on
        // failure; here we surface failures via console for now — adding
        // a global toast for this is a follow-up.
        void openPathInExternalApp(path, app).then((result) => {
          if (!result.success) {
            console.error(`Failed to open in ${app}:`, result.errorMessage ?? "(unknown error)");
          }
        });
      },

      hasUncommittedChanges: (ws): boolean => {
        // Diff data lives in the TanStack Query cache (keyed by
        // workspaceId + targetBranch). Reads from cache only — no fetch
        // is triggered. Returns false when no observer has populated the
        // cache yet, which matches the prior atom-based behavior
        // (descriptor renders the row as disabled until data arrives).
        const diff = getCachedWorkspaceDiff(ws.objectId, ws.targetBranch ?? null);
        const text = diff?.uncommittedDiff;
        return text != null && text.trim().length > 0;
      },
      hasOpenPr: (ws): boolean => {
        const prStatus = store.get(prStatusAtomFamily(ws.objectId));
        return prStatus?.prState === "open" && Boolean(prStatus.prWebUrl);
      },
      canCreatePr: (ws): boolean => {
        const prStatus = store.get(prStatusAtomFamily(ws.objectId));
        // Allow Create when there's no open PR yet — covers "none" and
        // "merged" (you can open a follow-up PR after a previous merge).
        return prStatus?.prState !== "open";
      },
      canOpenInOS: (): boolean => getBackendCapabilities().canOpenInOS,
      isMacUi: (): boolean => isMac(),
    }),
    [store],
  );
};
