import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./DiffSkeleton.module.scss";

// Deterministic ragged-right widths so the placeholder reads as code lines.
const ROW_WIDTH_PERCENTS = [62, 78, 45, 70, 55, 82, 38, 66, 50, 74, 42, 60] as const;

/**
 * Quiet placeholder for a diff that is about to render. Deliberately static and
 * low-contrast: no shimmer, no pulse — switching workspaces should not feel like
 * a page load.
 */
export const DiffSkeleton = (): ReactElement => {
  return (
    <Flex direction="column" gap="2" p="4" flexGrow="1" data-testid={ElementIds.DIFF_SKELETON}>
      {ROW_WIDTH_PERCENTS.map((widthPercent, index) => (
        <div key={index} className={styles.row} style={{ width: `${widthPercent}%` }} />
      ))}
    </Flex>
  );
};
