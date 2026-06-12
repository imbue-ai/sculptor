import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const BouncingDotsAnimation = (): ReactElement => {
  return (
    <span className={styles.bounce}>
      <span className={styles.bounceDot1} />
      <span className={styles.bounceDot2} />
      <span className={styles.bounceDot3} />
    </span>
  );
};
