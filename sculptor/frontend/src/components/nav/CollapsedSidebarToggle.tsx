import { useAtomValue, useSetAtom } from "jotai";
import { PanelLeftOpen } from "lucide-react";
import type { ReactElement } from "react";

import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";

import styles from "./CollapsedSidebarToggle.module.scss";
import { navSidebarCollapsedAtom } from "./navAtoms.ts";

/**
 * Top-left expand toggle for the nav sidebar, for pages that don't render the
 * WorkspaceBanner (Home, new-workspace). The banner owns this control on
 * workspace pages; without it, collapsing the sidebar on those pages would
 * leave no way to reopen it. Renders nothing while the sidebar is expanded.
 *
 * Positioned absolutely against PageLayout's relative root so it lands in the
 * top-left titlebar gutter; paddingLeft clears the macOS traffic-light buttons.
 */
export const CollapsedSidebarToggle = (): ReactElement | null => {
  const isNavCollapsed = useAtomValue(navSidebarCollapsedAtom);
  const setNavCollapsed = useSetAtom(navSidebarCollapsedAtom);

  if (!isNavCollapsed) {
    return null;
  }

  return (
    <div className={styles.collapsedSidebarToggle} style={{ paddingLeft: getTitleBarLeftPadding(false) }}>
      <TooltipIconButton
        tooltipText="Show sidebar"
        side="right"
        variant="ghost"
        size="1"
        color="gray"
        onClick={() => setNavCollapsed(false)}
        aria-label="Show sidebar"
        data-testid="topbar-sidebar-toggle"
      >
        <PanelLeftOpen size={16} />
      </TooltipIconButton>
    </div>
  );
};
