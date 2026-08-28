import { Skeleton, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { forwardRef } from "react";

import { ElementIds } from "~/api";

import styles from "./AlphaFileChip.module.scss";
import type { ChipData } from "./chipRow.types.ts";
import { getExecutingLabel } from "./chipRowUtils.ts";

type AlphaFileChipProps = {
  chipData: ChipData;
  isOpen: boolean;
  onToggle: () => void;
  onFocus: () => void;
  tabIndex: 0 | -1;
};

export const AlphaFileChip = forwardRef<HTMLButtonElement, AlphaFileChipProps>(
  ({ chipData, isOpen, onToggle, onFocus, tabIndex }, ref): ReactElement => {
    const { state, displayName, stats, isNewFile } = chipData;
    const isExecuting = state === "executing";

    const classNames = [styles.chip];

    if (isOpen) classNames.push(styles.chipOpen);
    if (isExecuting) classNames.push(styles.chipExecuting);
    if (state === "error") classNames.push(styles.chipError);

    const chip = (
      <button
        ref={ref}
        className={classNames.join(" ")}
        onClick={isExecuting ? undefined : onToggle}
        onFocus={onFocus}
        tabIndex={tabIndex}
        disabled={isExecuting}
        data-testid={ElementIds.ALPHA_CHAT_FILE_CHIP}
        data-tool-state={state === "executing" ? "initializing" : state}
      >
        <span className={state === "error" ? styles.chipErrorName : undefined}>{displayName}</span>

        {stats !== null ? (
          <>
            <span className={styles.statsAdded}>+{stats.added}</span>
            {!isNewFile && <span className={styles.statsRemoved}>-{stats.removed}</span>}
          </>
        ) : (
          isExecuting && (
            <>
              <Skeleton className={styles.statsSkeleton} />
              <Skeleton className={styles.statsSkeleton} />
            </>
          )
        )}
      </button>
    );

    if (isExecuting) {
      return (
        <Tooltip content={getExecutingLabel(chipData)} side="bottom">
          {chip}
        </Tooltip>
      );
    }

    return chip;
  },
);

AlphaFileChip.displayName = "AlphaFileChip";
