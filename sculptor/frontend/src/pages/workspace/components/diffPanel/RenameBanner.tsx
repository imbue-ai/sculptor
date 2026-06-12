import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./RenameBanner.module.scss";

type RenameBannerProps = {
  oldPath: string;
  newPath: string;
};

export const RenameBanner = ({ oldPath, newPath }: RenameBannerProps): ReactElement => {
  return (
    <Flex direction="column" flexShrink="0" data-testid={ElementIds.DIFF_RENAME_BANNER}>
      <div className={`${styles.line} ${styles.deletion}`}>
        <span className={styles.bar} />
        <span className={styles.text}>--- a/{oldPath}</span>
      </div>
      <div className={`${styles.line} ${styles.addition}`}>
        <span className={styles.bar} />
        <span className={styles.text}>+++ b/{newPath}</span>
      </div>
    </Flex>
  );
};
