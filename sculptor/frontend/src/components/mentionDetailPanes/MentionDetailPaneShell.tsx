import { Badge } from "@radix-ui/themes";
import classnames from "classnames";
import type { LucideIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";

import styles from "./MentionDetailPaneShell.module.scss";

export type DetailPaneColor = "amber" | "teal" | "violet" | "gray";

const ICON_CLASS_BY_COLOR: Record<DetailPaneColor, string> = {
  amber: styles.iconAmber,
  teal: styles.iconTeal,
  violet: styles.iconViolet,
  gray: styles.iconGray,
};

type MentionDetailPaneShellProps = {
  color: DetailPaneColor;
  icon: LucideIcon;
  title: ReactNode;
  // Whole-pane deleted state: mutes the icon to gray and strikes through the
  // title. Callers still decide whether to skip the body rows entirely or
  // to show a "deleted" placeholder in the body slot.
  deleted?: boolean;
  // Optional Radix Badge label. Color is inherited from `color`.
  badge?: string;
  // Free-form lines under the title. Each entry renders as a single line
  // with ellipsis truncation; use the `mono` flag for monospaced rows.
  body?: ReadonlyArray<{ text: string; mono?: boolean; key?: string }>;
  // Optional meta row rendered muted under the body (e.g. "3 workspaces").
  meta?: ReactNode;
};

/**
 * Shared layout primitive for the entity mention detail panes (agent,
 * workspace, repository) shown in chip hover cards. Centralises the icon +
 * title row, the optional badge, body lines, and meta footer so every pane
 * renders the same structure and spacing.
 *
 * Colour is driven by the `color` prop (maps to a type-specific icon tint).
 * When `deleted` is true the icon mutes to gray and the title is
 * strike-through — mirroring the deleted-state treatment in the chip.
 */
export const MentionDetailPaneShell = ({
  color,
  icon: Icon,
  title,
  deleted,
  badge,
  body,
  meta,
}: MentionDetailPaneShellProps): ReactElement => {
  const iconClass = deleted ? styles.iconGray : ICON_CLASS_BY_COLOR[color];
  return (
    <div className={styles.pane}>
      <div className={styles.header}>
        <Icon className={classnames(styles.icon, iconClass)} aria-hidden />
        <span className={classnames(styles.title, deleted && styles.strikethrough)}>{title}</span>
      </div>
      {badge !== undefined && (
        <Badge className={styles.badge} variant="soft" color={deleted ? "gray" : color}>
          {badge}
        </Badge>
      )}
      {body !== undefined && body.length > 0 && (
        <div className={styles.body}>
          {body.map((line, index) => (
            <span
              key={line.key ?? `${line.text}-${index}`}
              className={classnames(styles.bodyLine, line.mono && styles.mono)}
            >
              {line.text}
            </span>
          ))}
        </div>
      )}
      {meta !== undefined && <div className={styles.meta}>{meta}</div>}
    </div>
  );
};
