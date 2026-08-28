import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const CascadeAnimation = (): ReactElement => {
  return (
    <span className={styles.cascadeWrap}>
      <span className={styles.cascadeDot1} />
      <span className={styles.cascadeDot2} />
      <span className={styles.cascadeDot3} />
    </span>
  );
};
