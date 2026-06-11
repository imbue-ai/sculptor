import type { ReactElement, ReactNode } from "react";

import styles from "./PaletteFooter.module.scss";

type PaletteFooterProps = {
  /** Label for the ↵ hint (what Enter does here: "run", "add", …). */
  enterLabel: string;
  /** Label for the esc hint (what Escape does right now: "close", "back", "clear"). */
  escLabel: string;
  /** Optional right-aligned content (e.g. the Add Panel destination select). */
  children?: ReactNode;
};

/**
 * The shared keyboard-hint footer for cmd+k-style palettes (the command
 * palette, the Add Panel palette). Hints sit on the left; palette-specific
 * controls can be slotted in on the right.
 */
export const PaletteFooter = ({ enterLabel, escLabel, children }: PaletteFooterProps): ReactElement => (
  <div className={styles.footer}>
    <span className={styles.hint}>
      <kbd className={styles.key}>↑</kbd>
      <kbd className={styles.key}>↓</kbd> navigate
    </span>
    <span className={styles.hint}>
      <kbd className={styles.key}>↵</kbd> {enterLabel}
    </span>
    <span className={styles.hint}>
      <kbd className={styles.key}>esc</kbd> {escLabel}
    </span>
    <span className={styles.spacer} />
    {children}
  </div>
);
