import { useAtomValue, useSetAtom } from "jotai";
import { PanelLeftOpen } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";
import { sidebarCollapsedAtom } from "~/pages/workspace/layout/atoms/sidebar.ts";

import styles from "./CollapsedSidebarToggle.module.scss";

/**
 * Top-left expand toggle for the workspace sidebar, shown only while the
 * sidebar is collapsed. Without it, collapsing the sidebar would leave no way
 * to reopen it on routes (Home, new-workspace) that don't render their own
 * expand control. Renders nothing while the sidebar is expanded.
 *
 * Positioned absolutely in the top-left titlebar gutter; paddingLeft clears
 * the macOS traffic-light buttons.
 */
export const CollapsedSidebarToggle = (): ReactElement | null => {
  const isCollapsed = useAtomValue(sidebarCollapsedAtom);
  const setCollapsed = useSetAtom(sidebarCollapsedAtom);

  if (!isCollapsed) {
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
        onClick={() => setCollapsed(false)}
        aria-label="Show sidebar"
        data-testid={ElementIds.SIDEBAR_EXPAND_ICON}
      >
        <PanelLeftOpen size={16} />
      </TooltipIconButton>
    </div>
  );
};
