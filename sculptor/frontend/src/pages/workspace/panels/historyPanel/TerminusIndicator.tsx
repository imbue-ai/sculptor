import { Text } from "@radix-ui/themes";
import { MoreVertical } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import { SHORT_HASH_LENGTH } from "./commitGraph";
import styles from "./HistoryPanel.module.scss";

type TerminusIndicatorProps = {
  forkPoint: string | null;
  hideTopLine: boolean;
};

export const TerminusIndicator = ({ forkPoint, hideTopLine }: TerminusIndicatorProps): ReactElement => {
  const shortHash = forkPoint?.slice(0, SHORT_HASH_LENGTH);

  return (
    <div className={styles.terminus} data-testid={ElementIds.HISTORY_TERMINUS}>
      <div className={styles.terminusGraph}>
        <div className={`${styles.terminusLine} ${hideTopLine ? styles.graphLineHidden : ""}`} />
        <div className={styles.terminusDot} />
        <div className={styles.terminusLine} />
        <MoreVertical size={12} color="var(--gray-7)" />
      </div>
      <Text size="1" color="gray" className={styles.terminusLabel}>
        {shortHash ? `start of branch (${shortHash})` : "start of branch"}
      </Text>
    </div>
  );
};
