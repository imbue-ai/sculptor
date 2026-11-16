import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useCallback, useState } from "react";

import { getCurrentBranch, previewBranchName, WorkspaceInitializationStrategy } from "~/api";
import type { StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { isPiAvailableAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { repositoryWorkspaceVcsAtomFamily } from "~/common/state/atoms/repositoryWorkspaceVcs.ts";
import { createWorkspaceErrorToastAtom, ToastType } from "~/common/state/atoms/toasts.ts";
import { defaultModelAtom } from "~/common/state/atoms/userConfig.ts";
import { useCreateWorkspace } from "~/common/state/hooks/useCreateWorkspace.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import {
  hasRequiredCreationFields,
  resolveCreationMode,
  WORKSPACE_MODE_RULES,
} from "~/common/utils/workspaceModeRules.ts";
import {
  lastCreationSettingsByProjectIdAtom,
  lastWorkspaceCreationSettingsAtom,
  newWorkspaceDialogAtom,
} from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { resolveStoredAgentType } from "~/pages/workspace/layout/atoms/addPanel.ts";

type UseCreateWorkspaceFromSidebarReturn = {
  /** True while a direct-create is in flight. */
  isCreating: boolean;
  /**
   * The repo group's "+": create a workspace in that repo immediately, with a
   * freshly auto-generated unique branch name. The mode and source come from
   * the repo's own last creation (the repo's current branch is fetched when
   * none is remembered), and the agent type from the last creation anywhere.
   * Falls back to opening the dialog pre-selecting the repo when a
   * field the mode requires can't be resolved or the create fails.
   */
  createFromSidebar: (projectId: string) => Promise<void>;
};

// Each lookup resolves to "" when it fails, so one failure leaves only its own
// field unresolved.
const fetchCurrentBranchOrBlank = async (projectId: string): Promise<string> => {
  try {
    const { data } = await getCurrentBranch({ path: { project_id: projectId } });
    return data?.currentBranch ?? "";
  } catch {
    return "";
  }
};

const fetchFreshBranchNameOrBlank = async (inputs: {
  projectId: string;
  mode: WorkspaceInitializationStrategy;
}): Promise<string> => {
  try {
    // A blank workspace name makes the backend roll a random slug.
    const { data } = await previewBranchName({
      query: { project_id: inputs.projectId, workspace_name: "", mode: inputs.mode },
    });
    return data?.branchName ?? "";
  } catch {
    return "";
  }
};

/**
 * Decides between direct-create and opening the dialog for the repo group's
 * "+" button. Direct-create needs every field the mode requires — when one is
 * missing it defers to the dialog so the user can fill in the gaps (and so
 * branch collisions stay a dialog-only concern, since any branch direct-create
 * names is a freshly rolled random slug).
 */
export const useCreateWorkspaceFromSidebar = (): UseCreateWorkspaceFromSidebarReturn => {
  // State and hooks
  const store = useStore();
  const lastSettings = useAtomValue(lastWorkspaceCreationSettingsAtom);
  const lastSettingsByProjectId = useAtomValue(lastCreationSettingsByProjectIdAtom);
  const isPiAvailable = useAtomValue(isPiAvailableAtom);
  const defaultModel = useAtomValue(defaultModelAtom);
  const setModalState = useSetAtom(newWorkspaceDialogAtom);
  const setCreateWorkspaceErrorToast = useSetAtom(createWorkspaceErrorToastAtom);
  const { registrations } = useTerminalAgentRegistrations();
  const { isCreating, createWorkspace } = useCreateWorkspace();
  const [isPreparing, setIsPreparing] = useState<boolean>(false);

  // Functions and callbacks
  const createFromSidebar = useCallback(
    async (projectId: string): Promise<void> => {
      const remembered = lastSettingsByProjectId[projectId];
      const vcs = store.get(repositoryWorkspaceVcsAtomFamily(projectId));
      const mode = resolveCreationMode({ remembered: remembered?.mode, vcs });
      // The dialog waits for jj's availability, says why a jj workspace cannot
      // be created now, and links to where it can be fixed.
      if (
        (vcs === "jj-unavailable" || vcs === "jj-checking") &&
        mode === WorkspaceInitializationStrategy.JJ_WORKSPACE
      ) {
        setModalState({ open: true, presetProjectId: projectId });
        return;
      }
      // Normalize the remembered type, mirroring the dialog's seeding. A bare
      // "terminal" stays: it is a legitimate first-agent choice here. This
      // direct-create has no picker to steer to Settings, so a remembered "pi"
      // with no usable binary falls back to Claude rather than launching a pi
      // that cannot start.
      const seedAgentType = lastSettings?.agentType ?? "claude";
      const agentType: StoredAgentType =
        seedAgentType === "pi" && !isPiAvailable ? "claude" : resolveStoredAgentType(seedAgentType);

      const modeRules = WORKSPACE_MODE_RULES[mode];
      // A remembered source belongs to the mode it was picked for.
      const rememberedSourceBranch = (remembered?.mode === mode ? remembered.sourceBranch : undefined) ?? "";
      setIsPreparing(true);
      const doesSeedCurrentBranch =
        modeRules.sourceBranch.rule !== "unused" && modeRules.sourceBranch.seed === "current-branch";
      const sourceBranch =
        doesSeedCurrentBranch && !rememberedSourceBranch
          ? await fetchCurrentBranchOrBlank(projectId)
          : rememberedSourceBranch;
      const branchName =
        modeRules.branchName !== "unused" ? await fetchFreshBranchNameOrBlank({ projectId, mode }) : "";
      setIsPreparing(false);

      if (!hasRequiredCreationFields({ mode, branchName, sourceBranch })) {
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
      store,
      lastSettings,
      lastSettingsByProjectId,
      isPiAvailable,
      defaultModel,
      registrations,
      createWorkspace,
      setModalState,
      setCreateWorkspaceErrorToast,
    ],
  );

  return { isCreating: isCreating || isPreparing, createFromSidebar };
};
