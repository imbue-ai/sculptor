// A full-width sidebar nav row: leading icon + label, with active and disabled
// states. Used for the sidebar's fixed links (Home / Search / New Workspace /
// Settings) and the first-run "Add a repo" affordance.

import { Tooltip } from "@radix-ui/themes";
import type { LucideIcon } from "lucide-react";
import type { ReactElement } from "react";

import styles from "./NavItem.module.scss";

type NavItemProps = {
  icon: LucideIcon;
  label: string;
  isActive?: boolean;
  disabled?: boolean;
  /**
   * Tooltip shown on hover while the item is disabled, explaining why it
   * can't be used right now (e.g. no workspaces yet). Ignored when enabled.
   */
  disabledTooltip?: string;
  onClick: () => void;
  testId?: string;
};

export const NavItem = ({
  icon: Icon,
  label,
  isActive,
  disabled,
  disabledTooltip,
  onClick,
  testId,
}: NavItemProps): ReactElement => {
  const button = (
    <button
      type="button"
      className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
    >
      <Icon size={16} className={styles.navIcon} />
      <span className={styles.navLabel}>{label}</span>
    </button>
  );
  // Disabled buttons don't emit pointer events, so the tooltip anchors on a
  // wrapper span that still receives hover — this keeps the affordance
  // discoverable ("why can't I click this?") instead of a silent no-op.
  if (disabled && disabledTooltip) {
    return (
      <Tooltip content={disabledTooltip} side="right">
        <span className={styles.navItemTooltipAnchor}>{button}</span>
      </Tooltip>
    );
  }
  return button;
};
