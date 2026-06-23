import { useSetAtom } from "jotai";
import { useMemo } from "react";

import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { ensurePseudoTabAtom } from "~/common/state/atoms/workspaces.ts";
import { SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";

type OpenSettings = {
  (section?: string): void;
  (section: "repositories", focusRepoId: string): void;
  (section: "PANELS", focusPanelId: string): void;
};

/**
 * The single correct way to open the global Settings page: it both creates the
 * Settings pseudo-workspace-tab and navigates to the requested section, so no
 * caller has to remember to do the former. Callers must route through here
 * rather than navigating to `/settings` directly (see SCU-1581).
 */
export const useOpenSettings = (): OpenSettings => {
  const { navigateToGlobalSettings, navigateToRepoSetupCommand, navigateToPanelSettings } = useImbueNavigate();
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);

  return useMemo<OpenSettings>(() => {
    function openSettings(section?: string): void;
    function openSettings(section: "repositories", focusRepoId: string): void;
    function openSettings(section: "PANELS", focusPanelId: string): void;
    function openSettings(section?: string, focusId?: string): void {
      ensurePseudoTab(SETTINGS_TAB_ID);
      if (focusId !== undefined && section === "repositories") {
        navigateToRepoSetupCommand(focusId);
      } else if (focusId !== undefined && section === "PANELS") {
        navigateToPanelSettings(focusId);
      } else {
        navigateToGlobalSettings(section);
      }
    }
    return openSettings;
  }, [ensurePseudoTab, navigateToGlobalSettings, navigateToRepoSetupCommand, navigateToPanelSettings]);
};
