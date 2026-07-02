import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useState } from "react";

import { previewBranchName, WorkspaceInitializationStrategy } from "~/api";
import type { StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { defaultModelAtom, isPiAgentEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { useCreateWorkspace } from "~/common/state/hooks/useCreateWorkspace.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import {
  lastWorkspaceCreationSettingsAtom,
  newWorkspaceModalAtom,
} from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { resolveStoredAgentType } from "~/components/sections/addPanelCore.ts";

type UseCreateWorkspaceFromSidebarReturn = {
  /** True while a direct-create is in flight. */
  isCreating: boolean;
  /**
   * The sidebar new-workspace button: create a workspace immediately,
   * reusing the last creation settings (repo / source branch / agent type /
   * init strategy) plus a freshly auto-generated unique branch name. Falls back
   * to opening the dialog when there are no last settings yet (first-ever
   * create) or when branch auto-generation is unavailable.
   */
  createFromSidebar: () => Promise<void>;
};

/**
 * Decides between direct-create and opening the dialog for the sidebar
 * new-workspace button. Direct-create needs both a remembered set of settings
 * and a fresh auto-branch — when either is missing it defers to the dialog so
 * the user can fill in the gaps (and so branch collisions stay a dialog-only
 * concern, since direct-create always uses a fresh unique branch).
 */
export const useCreateWorkspaceFromSidebar = (): UseCreateWorkspaceFromSidebarReturn => {
  // State and hooks
  const lastSettings = useAtomValue(lastWorkspaceCreationSettingsAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const defaultModel = useAtomValue(defaultModelAtom);
  const setModalState = useSetAtom(newWorkspaceModalAtom);
  const { registrations } = useTerminalAgentRegistrations();
  const { isCreating, createWorkspace } = useCreateWorkspace();
  const [isGeneratingBranch, setIsGeneratingBranch] = useState<boolean>(false);

  // Functions and callbacks
  const createFromSidebar = useCallback(async (): Promise<void> => {
    // No prior create to reuse — let the dialog gather the first set of
    // settings (and persist them for next time).
    if (!lastSettings) {
      setModalState({ open: true });
      return;
    }

    const mode = lastSettings.initStrategy;
    // The shared pi-disabled fallback, mirroring the dialog's seeding. A bare
    // "terminal" stays: it is a legitimate first-agent choice here.
    const agentType: StoredAgentType = resolveStoredAgentType(lastSettings.agentType, isPiAgentEnabled);

    // In-place reuses the current branch, so it never needs an auto-generated
    // branch name. Worktree/clone do — generate a fresh unique one (a blank
    // workspace name makes the backend roll a random slug), falling back to the
    // dialog if the preview is unavailable.
    let branchName = "";
    if (mode !== WorkspaceInitializationStrategy.IN_PLACE) {
      setIsGeneratingBranch(true);
      try {
        const result = await previewBranchName({
          query: { project_id: lastSettings.projectId, workspace_name: "", mode },
        });
        branchName = result.data?.branchName ?? "";
      } catch {
        branchName = "";
      } finally {
        setIsGeneratingBranch(false);
      }

      if (!branchName) {
        setModalState({ open: true, presetProjectId: lastSettings.projectId });
        return;
      }
    }

    const createResult = await createWorkspace({
      projectId: lastSettings.projectId,
      workspaceName: "",
      prompt: "",
      mode,
      sourceBranch: lastSettings.sourceBranch,
      branchName,
      agentTypeValue: agentType,
      registrations,
      defaultModel,
    });

    // Surface any failure in the dialog (pre-selecting the repo) so the user can
    // see the error and retry from a full form rather than being left with a
    // silent no-op.
    if (!createResult.ok) {
      setModalState({ open: true, presetProjectId: lastSettings.projectId });
    }
  }, [lastSettings, isPiAgentEnabled, defaultModel, registrations, createWorkspace, setModalState]);

  return { isCreating: isCreating || isGeneratingBranch, createFromSidebar };
};
