import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./StreamingCursor.module.scss";

export const StreamingCursor = (): ReactElement => {
  return <span className={styles.streamingCursor} data-testid={ElementIds.STREAMING_CURSOR} />;
};
