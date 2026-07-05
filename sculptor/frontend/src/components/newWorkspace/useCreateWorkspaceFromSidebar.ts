import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useState } from "react";

import { getCurrentBranch, previewBranchName, WorkspaceInitializationStrategy } from "~/api";
import type { StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { createWorkspaceErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { defaultModelAtom, isPiAgentEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { useCreateWorkspace } from "~/common/state/hooks/useCreateWorkspace.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import {
  lastWorkspaceCreationSettingsAtom,
  newWorkspaceModalAtom,
} from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { resolveStoredAgentType } from "~/components/sections/addPanelCore.ts";
import { ToastType } from "~/components/Toast.tsx";

type UseCreateWorkspaceFromSidebarReturn = {
  /** True while a direct-create is in flight. */
  isCreating: boolean;
  /**
   * The repo group's "+": create a workspace in that repo immediately, with a
   * freshly auto-generated unique branch name. Settings come from the last
   * creation when it targeted the same repo; otherwise the repo's current
   * branch is fetched and the last mode/agent type (or the defaults) are
   * reused. Falls back to opening the dialog pre-selecting the repo when the
   * branch can't be resolved or the create fails.
   */
  createFromSidebar: (projectId: string) => Promise<void>;
};

/**
 * Decides between direct-create and opening the dialog for the repo group's
 * "+" button. Direct-create needs a source branch and a fresh auto-branch —
 * when either is missing it defers to the dialog so the user can fill in the
 * gaps (and so branch collisions stay a dialog-only concern, since
 * direct-create always uses a fresh unique branch).
 */
export const useCreateWorkspaceFromSidebar = (): UseCreateWorkspaceFromSidebarReturn => {
  // State and hooks
  const lastSettings = useAtomValue(lastWorkspaceCreationSettingsAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const defaultModel = useAtomValue(defaultModelAtom);
  const setModalState = useSetAtom(newWorkspaceModalAtom);
  const setCreateWorkspaceErrorToast = useSetAtom(createWorkspaceErrorToastAtom);
  const { registrations } = useTerminalAgentRegistrations();
  const { isCreating, createWorkspace } = useCreateWorkspace();
  const [isPreparing, setIsPreparing] = useState<boolean>(false);

  // Functions and callbacks
  const createFromSidebar = useCallback(
    async (projectId: string): Promise<void> => {
      // Last settings only transfer wholesale when they were made for THIS
      // repo — a source branch remembered from another repo may not exist here.
      const sameRepoSettings = lastSettings?.projectId === projectId ? lastSettings : null;
      const mode = lastSettings?.initStrategy ?? WorkspaceInitializationStrategy.WORKTREE;
      // The shared pi-disabled fallback, mirroring the dialog's seeding. A bare
      // "terminal" stays: it is a legitimate first-agent choice here.
      const agentType: StoredAgentType = resolveStoredAgentType(lastSettings?.agentType ?? "claude", isPiAgentEnabled);

      setIsPreparing(true);
      let sourceBranch = sameRepoSettings?.sourceBranch ?? "";
      // In-place reuses the current branch, so it never needs an auto-generated
      // branch name. Worktree/clone do — generate a fresh unique one (a blank
      // workspace name makes the backend roll a random slug).
      let branchName = "";
      try {
        if (!sourceBranch) {
          const branchInfo = await getCurrentBranch({ path: { project_id: projectId } });
          sourceBranch = branchInfo.data?.currentBranch ?? "";
        }

        if (mode !== WorkspaceInitializationStrategy.IN_PLACE) {
          const result = await previewBranchName({
            query: { project_id: projectId, workspace_name: "", mode },
          });
          branchName = result.data?.branchName ?? "";
        }
      } catch {
        // Fall through to the dialog below with whatever is missing.
      } finally {
        setIsPreparing(false);
      }

      const doesNeedBranchName = mode !== WorkspaceInitializationStrategy.IN_PLACE;
      if (!sourceBranch || (doesNeedBranchName && !branchName)) {
        setModalState({ open: true, presetProjectId: projectId });
        return;
      }

      const createResult = await createWorkspace({
        projectId,
        workspaceName: "",
        prompt: "",
        mode,
        sourceBranch,
        branchName,
        agentTypeValue: agentType,
        registrations,
        defaultModel,
      });

      // A direct-create failure has no form on screen to show the error inline,
      // so raise a toast for the "why" and open the dialog (pre-selecting the
      // repo) as a retry surface — rather than leaving a silent no-op.
      if (!createResult.ok) {
        setCreateWorkspaceErrorToast({
          title: "Failed to create workspace",
          description: "The workspace could not be created. Adjust the details and try again.",
          type: ToastType.ERROR,
          action: null,
        });
        setModalState({ open: true, presetProjectId: projectId });
      }
    },
    [
      lastSettings,
      isPiAgentEnabled,
      defaultModel,
      registrations,
      createWorkspace,
      setModalState,
      setCreateWorkspaceErrorToast,
    ],
  );

  return { isCreating: isCreating || isPreparing, createFromSidebar };
};
