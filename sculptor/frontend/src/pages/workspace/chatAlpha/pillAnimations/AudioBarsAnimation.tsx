import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const AudioBarsAnimation = (): ReactElement => {
  return (
    <span className={styles.bars}>
      <span className={styles.audioBar1} />
      <span className={styles.audioBar2} />
      <span className={styles.audioBar3} />
    </span>
  );
};
