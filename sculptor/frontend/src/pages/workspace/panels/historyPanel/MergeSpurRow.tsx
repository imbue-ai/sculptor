import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import { SHORT_HASH_LENGTH } from "./commitGraph";
import styles from "./HistoryPanel.module.scss";

type MergeSpurRowProps = {
  parentHash: string;
  /** When true, the spur connects to nested child commits instead of showing an ellipsis + hash. */
  connected?: boolean;
};

/**
 * A compact row rendered below a merge commit showing the second parent as a
 * curved spur branching off the main graph line.
 *
 * In standalone mode (default): ends in an ellipsis + short hash.
 * In connected mode: the curve targets the nested branch graph column.
 */
export const MergeSpurRow = ({ parentHash, connected }: MergeSpurRowProps): ReactElement => {
  const shortHash = parentHash.slice(0, SHORT_HASH_LENGTH);

  return (
    <div className={styles.mergeSpurRow} data-testid={ElementIds.HISTORY_MERGE_SPUR}>
      <svg className={styles.mergeSpurSvg} viewBox="0 0 48 24">
        {/* Main vertical line continuing down */}
        <line x1="10" y1="0" x2="10" y2="24" stroke="var(--gray-7)" strokeWidth="2" />
        {connected ? (
          /* Curve from main line to nested branch graph column (center at x=30) */
          <path d="M 10 0 C 10 14, 30 10, 30 24" stroke="var(--gray-7)" strokeWidth="1.5" fill="none" />
        ) : (
          <>
            {/* Curved spur from the main line going right to ellipsis */}
            <path d="M 10 0 C 10 12, 20 18, 32 18" stroke="var(--gray-7)" strokeWidth="1.5" fill="none" />
            {/* Three-dot ellipsis at the end of the spur */}
            <circle cx="34" cy="18" r="1.5" fill="var(--gray-7)" />
            <circle cx="39" cy="18" r="1.5" fill="var(--gray-7)" />
            <circle cx="44" cy="18" r="1.5" fill="var(--gray-7)" />
          </>
        )}
      </svg>
      {!connected && <span className={styles.mergeSpurLabel}>{shortHash}</span>}
    </div>
  );
};
