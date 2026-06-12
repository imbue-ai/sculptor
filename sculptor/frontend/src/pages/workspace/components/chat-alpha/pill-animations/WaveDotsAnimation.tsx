import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const WaveDotsAnimation = (): ReactElement => {
  return (
    <span className={styles.wave}>
      <span className={styles.waveDot1} />
      <span className={styles.waveDot2} />
      <span className={styles.waveDot3} />
    </span>
  );
};
