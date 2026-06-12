import type { ReactElement } from "react";

import styles from "./KeyboardHint.module.scss";

type KeyboardHintProps = {
  keys: string;
  label: string;
};

export const KeyboardHint = ({ keys, label }: KeyboardHintProps): ReactElement => (
  <div className={styles.hint}>
    <kbd className={styles.kbd}>{keys}</kbd> {label}
  </div>
);
