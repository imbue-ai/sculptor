import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const SparkAnimation = (): ReactElement => {
  return (
    <span className={styles.sparkWrap}>
      <span className={styles.sparkDot1} />
      <span className={styles.sparkDot2} />
      <span className={styles.sparkDot3} />
    </span>
  );
};
