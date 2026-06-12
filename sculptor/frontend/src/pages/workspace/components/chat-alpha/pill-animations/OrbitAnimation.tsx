import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const OrbitAnimation = (): ReactElement => {
  return (
    <span className={styles.orbit}>
      <span className={styles.orbitTrack}>
        <span className={styles.orbitDot1} />
        <span className={styles.orbitDot2} />
      </span>
    </span>
  );
};
