import type { ReactElement } from "react";

import styles from "./PillAnimations.module.scss";

export const SpinnerAnimation = (): ReactElement => {
  return <span className={styles.spinner} />;
};
