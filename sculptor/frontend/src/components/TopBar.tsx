import { Flex } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import { HelpCircleIcon, HomeIcon, SearchIcon, SettingsIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect } from "react";
import { useLocation } from "react-router-dom";

import { ElementIds } from "../api";
import { useKeybindingDisplayText } from "../common/keybindings/hooks.ts";
import { useImbueLocation, useImbueNavigate } from "../common/NavigateUtils.ts";
import { ensurePseudoTabAtom, lastNonHomeLocationAtom } from "../common/state/atoms/workspaces.ts";
import { useHelpDialog } from "../common/state/hooks/useHelpDialog.ts";
import { useHomeToggle } from "../common/state/hooks/useHomeToggle.ts";
import { getTitleBarLeftPadding } from "../electron/utils.ts";
import { ClosedWorkspacesPill } from "./ClosedWorkspacesPill.tsx";
import { useCommandPalette } from "./CommandPalette";
import { TooltipIconButton } from "./TooltipIconButton.tsx";
import styles from "./TopBar.module.scss";
import { SETTINGS_TAB_ID } from "./workspaceTabIds.ts";
import { WorkspaceTabs } from "./WorkspaceTabs.tsx";

export const TopBar = (): ReactElement => {
  const { navigateToGlobalSettings } = useImbueNavigate();
  const location = useLocation();
  const { isHomeRoute } = useImbueLocation();
  const { toggle: toggleCommandPalette } = useCommandPalette();
  const { showHelpDialog } = useHelpDialog();
  // Read the live binding from the registry so the tooltip stays accurate
  // when the user remaps Cmd+K in Settings.
  const commandPaletteShortcut = useKeybindingDisplayText("command_palette");
  const homeShortcut = useKeybindingDisplayText("home");
  const helpShortcut = useKeybindingDisplayText("help");
  const settingsShortcut = useKeybindingDisplayText("settings");
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);
  const setLastNonHomeLocation = useSetAtom(lastNonHomeLocationAtom);
  const { toggleHome, isToggleNoOp: isHomeToggleNoOp } = useHomeToggle();

  // Remember the last path the user was on outside /home so the Home
  // icon (and the global "home" keybinding) can toggle back to it.
  // Updated whenever the pathname changes and isn't /home — including
  // the initial mount on a workspace URL.
  useEffect(() => {
    if (!isHomeRoute) {
      setLastNonHomeLocation(location.pathname + location.search);
    }
  }, [isHomeRoute, location.pathname, location.search, setLastNonHomeLocation]);

  const handleOpenSettings = useCallback((): void => {
    ensurePseudoTab(SETTINGS_TAB_ID);
    navigateToGlobalSettings();
  }, [ensurePseudoTab, navigateToGlobalSettings]);

  return (
    <Flex
      align="center"
      gap="3"
      pr="3"
      pl={getTitleBarLeftPadding(false)}
      justify="between"
      className={styles.container}
      flexShrink="0"
      height="40px"
      data-testid={ElementIds.TOP_BAR}
    >
      <TooltipIconButton
        tooltipText={<>Home {homeShortcut && <kbd className={styles.tooltipKbd}>{homeShortcut}</kbd>}</>}
        variant={isHomeRoute ? "soft" : "ghost"}
        size="1"
        onClick={toggleHome}
        aria-label="Home"
        aria-pressed={isHomeRoute}
        // On /home with nowhere to toggle back to, the click is a no-op —
        // reflect that in the DOM rather than silently swallowing it. The
        // handler keeps its own early-return as the real gate.
        aria-disabled={isHomeToggleNoOp}
        data-testid={ElementIds.HOME_BUTTON}
        className={styles.homeButton}
      >
        <HomeIcon size={16} />
      </TooltipIconButton>
      <WorkspaceTabs />
      <Flex flexShrink="0" gap="3">
        <ClosedWorkspacesPill />
        <TooltipIconButton
          tooltipText={
            <>
              Command palette{" "}
              {commandPaletteShortcut && <kbd className={styles.tooltipKbd}>{commandPaletteShortcut}</kbd>}
            </>
          }
          variant="ghost"
          size="1"
          onClick={toggleCommandPalette}
          aria-label="Toggle command palette"
          data-testid={ElementIds.COMMAND_PALETTE_OPEN_BUTTON}
        >
          <SearchIcon size={16} />
        </TooltipIconButton>
        <TooltipIconButton
          tooltipText={<>Settings {settingsShortcut && <kbd className={styles.tooltipKbd}>{settingsShortcut}</kbd>}</>}
          variant="ghost"
          size="1"
          onClick={handleOpenSettings}
          aria-label="Settings"
          data-testid={ElementIds.SETTINGS_BUTTON}
        >
          <SettingsIcon size={16} />
        </TooltipIconButton>
        <TooltipIconButton
          tooltipText={<>Help {helpShortcut && <kbd className={styles.tooltipKbd}>{helpShortcut}</kbd>}</>}
          variant="ghost"
          size="1"
          onClick={showHelpDialog}
          aria-label="Help"
          data-testid={ElementIds.HELP_BUTTON}
        >
          <HelpCircleIcon size={16} />
        </TooltipIconButton>
      </Flex>
    </Flex>
  );
};
