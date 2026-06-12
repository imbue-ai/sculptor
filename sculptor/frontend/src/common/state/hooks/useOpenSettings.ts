import { useSetAtom } from "jotai";
import { useMemo } from "react";

import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { ensurePseudoTabAtom } from "~/common/state/atoms/workspaces.ts";
import { SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";

type OpenSettings = {
  (section?: string): void;
  (section: "repositories", focusRepoId: string): void;
};

export const useOpenSettings = (): OpenSettings => {
  const { navigateToGlobalSettings, navigateToRepoSetupCommand } = useImbueNavigate();
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);

  return useMemo<OpenSettings>(() => {
    function openSettings(section?: string): void;
    function openSettings(section: "repositories", focusRepoId: string): void;
    function openSettings(section?: string, focusRepoId?: string): void {
      ensurePseudoTab(SETTINGS_TAB_ID);
      if (focusRepoId !== undefined) {
        navigateToRepoSetupCommand(focusRepoId);
      } else {
        navigateToGlobalSettings(section);
      }
    }
    return openSettings;
  }, [ensurePseudoTab, navigateToGlobalSettings, navigateToRepoSetupCommand]);
};
