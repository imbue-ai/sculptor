// The one shared "system line" language used for every background-process
// system moment in the transcript: triggered turns (monitor events, process
// exits) and the restart notice all render as the same bare line. Matches the
// real app's workspace-intro info-line style (AlphaChatIntro): a dim gray icon
// + gray text (name bolded, detail in mono) + a right-aligned mono time. No
// left rule, no box; the single line ellipsizes with the time pinned right.
//
// Presentational only — the caller supplies the icon, the copy, and the
// already-formatted time string.
import type { LucideIcon } from "lucide-react";
import type { ReactElement } from "react";

import { optional } from "~/common/Utils";

import styles from "./BackgroundSystemLine.module.scss";

type BackgroundSystemLineProps = {
  icon?: LucideIcon;
  name: string;
  detail?: string;
  time: string;
};

export const BackgroundSystemLine = ({ icon: Icon, name, detail, time }: BackgroundSystemLineProps): ReactElement => {
  return (
    <div className={styles.line}>
      {Icon !== undefined ? (
        <span className={styles.icon}>
          <Icon size={14} aria-hidden="true" />
        </span>
      ) : undefined}
      <span className={styles.label}>
        <strong className={styles.name}>{name}</strong>
        {optional(detail !== undefined, <span className={styles.detail}> {detail}</span>)}
      </span>
      {optional(time !== "", <span className={styles.time}>{time}</span>)}
    </div>
  );
};
