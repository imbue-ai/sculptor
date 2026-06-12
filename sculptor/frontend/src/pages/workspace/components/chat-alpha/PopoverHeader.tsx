import type { ReactElement, ReactNode } from "react";

import styles from "./PopoverHeader.module.scss";

type PopoverHeaderProps = {
  /** Primary descriptive content — the most useful single piece of context for this popover. */
  title: ReactNode;
  /** Optional right-aligned secondary metadata (duration, line count, match count, etc.). */
  meta?: ReactNode;
  /** Optional right-aligned action buttons. */
  actions?: ReactNode;
};

/**
 * Header bar for the top of a tool/bash popover. Holds the descriptive
 * title (left), optional secondary metadata, and any action buttons (right).
 * Designed to be `flex-shrink: 0` so when the popover body scrolls, the
 * title stays visible.
 */
export const PopoverHeader = ({ title, meta, actions }: PopoverHeaderProps): ReactElement => (
  <div className={styles.header}>
    <span className={styles.title}>{title}</span>
    {(meta !== undefined || actions !== undefined) && (
      <span className={styles.aside}>
        {meta !== undefined && <span className={styles.meta}>{meta}</span>}
        {actions !== undefined && <span className={styles.actions}>{actions}</span>}
      </span>
    )}
  </div>
);
