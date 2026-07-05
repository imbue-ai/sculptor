import { useSetAtom } from "jotai";
import { useMemo } from "react";

import { useImbueNavigate } from "~/common/hooks/navigation.ts";
import { ensurePseudoTabAtom } from "~/common/state/atoms/workspaces.ts";
import { SETTINGS_TAB_ID } from "~/common/utils/workspaceTabIds.ts";

// `section` is a `SettingsSection` id from `~/pages/settings/sections.ts`.
// `SettingsPage` matches the `?section=` query param against those ids
// case-sensitively, so these literals MUST stay uppercase to match (SCU-1599).
type OpenSettings = {
  (section?: string): void;
  (section: "REPOSITORIES", focusRepoId: string): void;
};

/**
 * The single correct way to open the global Settings page: it both creates the
 * Settings pseudo-workspace-tab and navigates to the requested section, so no
 * caller has to remember to do the former. Callers must route through here
 * rather than navigating to `/settings` directly (see SCU-1581).
 */
export const useOpenSettings = (): OpenSettings => {
  const { navigateToGlobalSettings, navigateToRepoSetupCommand } = useImbueNavigate();
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);

  return useMemo<OpenSettings>(() => {
    function openSettings(section?: string): void;
    function openSettings(section: "REPOSITORIES", focusRepoId: string): void;
    function openSettings(section?: string, focusId?: string): void {
      ensurePseudoTab(SETTINGS_TAB_ID);
      if (focusId !== undefined && section === "REPOSITORIES") {
        navigateToRepoSetupCommand(focusId);
      } else {
        navigateToGlobalSettings(section);
      }
    }
    return openSettings;
  }, [ensurePseudoTab, navigateToGlobalSettings, navigateToRepoSetupCommand]);
};
