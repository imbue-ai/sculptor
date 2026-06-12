import { Spinner } from "@radix-ui/themes";
import { ArrowRightFromLine, Check, X } from "lucide-react";
import type { ReactElement } from "react";

import styles from "./bashBlockStyles.module.scss";

export type BashBlockState = "executing" | "completed" | "error";

type BashStatusBadgeProps = {
  state: BashBlockState;
  isBackground: boolean;
  duration: string;
  testId: string;
};

export const BashStatusBadge = ({ state, isBackground, duration, testId }: BashStatusBadgeProps): ReactElement => {
  if (state === "executing") {
    return (
      <span className={`${styles.badge} ${styles.badgeRunning}`} data-testid={testId}>
        {duration}
        <span className={styles.badgeIcon}>
          <Spinner size="1" />
        </span>
      </span>
    );
  }

  if (state === "error") {
    return (
      <span className={`${styles.badge} ${styles.badgeError}`} data-testid={testId}>
        {duration}
        <span className={styles.badgeIcon}>
          <X size={12} />
        </span>
      </span>
    );
  }

  const successText = isBackground ? "background" : duration;

  return (
    <span className={`${styles.badge} ${styles.badgeSuccess}`} data-testid={testId}>
      {successText}
      <span className={styles.badgeIcon}>{isBackground ? <ArrowRightFromLine size={12} /> : <Check size={12} />}</span>
    </span>
  );
};
