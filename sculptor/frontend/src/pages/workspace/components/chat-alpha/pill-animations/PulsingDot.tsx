import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const PulsingDot = (): ReactElement => {
  return (
    <span className={styles.pulsingDot}>
      <span className={styles.pulsingDotOuter} />
      <span className={styles.pulsingDotInner} />
    </span>
  );
};
