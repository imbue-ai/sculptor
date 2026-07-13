import { IconButton } from "@radix-ui/themes";
import { SquareMenu } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./MobileHomeHeader.module.scss";

type MobileHomeHeaderProps = {
  onOpenDrawer: () => void;
};

/**
 * MobileHomeHeader — replaces the global TopBar on the mobile Home view,
 * mirroring the MobileWorkspaceHeader chrome. Left: ☰ opens the drawer (Home /
 * Settings / workspaces). Center: the "Home" title. Owns the top safe-area
 * inset (H4) now that the TopBar is suppressed. The body keeps the existing Home
 * content (recent-workspaces search + list).
 */
export const MobileHomeHeader = ({ onOpenDrawer }: MobileHomeHeaderProps): ReactElement => {
  return (
    <header className={`mobileTheme ${styles.header}`} data-testid={ElementIds.MOBILE_HOME_HEADER}>
      <IconButton
        variant="ghost"
        color="gray"
        className={styles.iconButton}
        aria-label="Open menu"
        onClick={onOpenDrawer}
      >
        <SquareMenu size={22} />
      </IconButton>

      <div className={styles.title}>
        <div className={styles.name}>Home</div>
      </div>

      {/* Invisible match for the menu button so the title stays truly centered. */}
      <span className={styles.spacer} aria-hidden="true" />
    </header>
  );
};
