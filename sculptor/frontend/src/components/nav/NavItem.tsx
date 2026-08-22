// A full-width sidebar nav row: leading icon + label, with active and disabled
// states. Used for the sidebar's fixed links (Home / Search / New Workspace /
// Settings) and the first-run "Add a repo" affordance.

import { Tooltip } from "@radix-ui/themes";
import type { LucideIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ShortcutHint } from "~/components/ShortcutHint.tsx";

import styles from "./NavItem.module.scss";

type NavItemProps = {
  icon: LucideIcon;
  label: string;
  isActive?: boolean;
  disabled?: boolean;
  /**
   * Tooltip shown on hover or keyboard focus while the item is disabled,
   * explaining why it can't be used right now. Ignored when enabled.
   */
  disabledTooltip?: string;
  /**
   * Raw keybinding for the action (e.g. "Meta+K"), shown as a quiet right-aligned
   * hint. Omitted for actions with no shortcut.
   */
  shortcut?: string | null;
  onClick: () => void;
  testId?: string;
};

export const NavItem = ({
  icon: Icon,
  label,
  isActive,
  disabled,
  disabledTooltip,
  shortcut,
  onClick,
  testId,
}: NavItemProps): ReactElement => {
  const button = (
    <button
      type="button"
      className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
      // aria-disabled (not the native disabled attribute) keeps the row focusable, so
      // keyboard users can land on it to discover why it's unavailable and the
      // explanatory tooltip fires on focus as well as hover. An aria-disabled button
      // still emits events, so the click is guarded here.
      aria-disabled={disabled || undefined}
      onClick={disabled ? undefined : onClick}
      data-testid={testId}
    >
      <Icon size={16} className={styles.navIcon} />
      <span className={styles.navLabel}>{label}</span>
      {shortcut ? <ShortcutHint binding={shortcut} className={styles.navShortcut} /> : null}
    </button>
  );
  // The row stays focusable while disabled (aria-disabled), so the tooltip anchors on
  // the button itself and shows on hover or keyboard focus — keeping the "why can't I
  // use this?" affordance discoverable instead of a silent no-op.
  if (disabled && disabledTooltip) {
    return (
      <Tooltip content={disabledTooltip} side="right">
        {button}
      </Tooltip>
    );
  }
  return button;
};
