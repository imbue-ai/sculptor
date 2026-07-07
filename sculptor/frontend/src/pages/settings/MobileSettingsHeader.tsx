import { IconButton } from "@radix-ui/themes";
import { ChevronLeft } from "lucide-react";
import type { ReactElement } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useImbueNavigate } from "~/common/NavigateUtils.ts";

import styles from "./MobileSettingsHeader.module.scss";

/**
 * MobileSettingsHeader — replaces the global TopBar on the mobile Settings
 * view, mirroring the MobileWorkspaceHeader / overlay chrome so the page reads
 * as part of the same mobile shell. Left: a back chevron that returns to the
 * previous route (Settings is reached from the Workspace ⋮ menu), falling back
 * to Home on a cold deep-link with no history to pop. Center: the "Settings"
 * title. Owns the top safe-area inset (H4) now that the TopBar is suppressed.
 */
export const MobileSettingsHeader = (): ReactElement => {
  const navigate = useNavigate();
  const location = useLocation();
  const { navigateToHome } = useImbueNavigate();

  const handleBack = (): void => {
    // `key === "default"` marks the first history entry (e.g. a cold deep-link
    // straight to /settings), so there is nothing to pop back to — go Home.
    if (location.key === "default") {
      navigateToHome();
    } else {
      navigate(-1);
    }
  };

  return (
    <header className={`mobileTheme ${styles.header}`}>
      <IconButton variant="ghost" color="gray" className={styles.iconButton} aria-label="Back" onClick={handleBack}>
        <ChevronLeft size={22} />
      </IconButton>

      <div className={styles.title}>
        <div className={styles.name}>Settings</div>
      </div>

      {/* Invisible match for the back button so the title stays truly centered. */}
      <span className={styles.spacer} aria-hidden="true" />
    </header>
  );
};
