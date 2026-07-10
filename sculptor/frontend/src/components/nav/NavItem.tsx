// A full-width sidebar nav row: leading icon + label, with an active state.
// Used for the sidebar's fixed links (Home / Search / New Workspace /
// Settings) and the first-run "Add a repo" affordance.

import type { LucideIcon } from "lucide-react";
import type { ReactElement } from "react";

import styles from "./NavItem.module.scss";

type NavItemProps = {
  icon: LucideIcon;
  label: string;
  isActive?: boolean;
  onClick: () => void;
  testId?: string;
};

export const NavItem = ({ icon: Icon, label, isActive, onClick, testId }: NavItemProps): ReactElement => {
  return (
    <button
      type="button"
      className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
      onClick={onClick}
      data-testid={testId}
    >
      <Icon size={16} className={styles.navIcon} />
      <span className={styles.navLabel}>{label}</span>
    </button>
  );
};
