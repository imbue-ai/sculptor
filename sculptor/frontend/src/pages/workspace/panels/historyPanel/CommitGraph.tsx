import type { ReactElement } from "react";

import styles from "./HistoryPanel.module.scss";

type CommitGraphProps = {
  isHead: boolean;
  hideTopLine: boolean;
};

export const CommitGraph = ({ isHead, hideTopLine }: CommitGraphProps): ReactElement => (
  <div className={styles.graphColumn}>
    <div className={`${styles.graphLineTop} ${hideTopLine ? styles.graphLineHidden : ""}`} />
    <div className={`${styles.graphDot} ${isHead ? styles.graphDotHead : ""}`} />
    <div className={styles.graphLineBottom} />
  </div>
);
