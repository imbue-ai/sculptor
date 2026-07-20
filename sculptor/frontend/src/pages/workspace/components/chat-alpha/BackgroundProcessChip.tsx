// Presentational chip for the floating bottom bar (just left of the StatusPill),
// shown while background processes are running. Status is conveyed without
// color — the dot pulses gently while something runs. Pure props so it renders
// standalone in Storybook and tests; the live-data container that counts
// running processes and anchors the details popover lives with the alpha chat
// wiring. forwardRef so a popover trigger can anchor to the chip's DOM node.
import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";
import { forwardRef } from "react";

import { mergeClasses, optional } from "~/common/Utils";

import styles from "./BackgroundProcessChip.module.scss";

type BackgroundProcessChipButtonProps = {
  runningCount: number;
  isOpen: boolean;
  onClick?: () => void;
};

export const BackgroundProcessChipButton = forwardRef<HTMLDivElement, BackgroundProcessChipButtonProps>(
  ({ runningCount, isOpen, onClick }, ref): ReactElement => {
    return (
      <div ref={ref} className={styles.chip} data-testid="background-process-chip" onClick={onClick}>
        <span className={styles.dot} />
        <span className={styles.label}>
          {runningCount} process{runningCount === 1 ? "" : "es"}
        </span>
        <span className={mergeClasses(styles.chevron, optional(isOpen, styles.chevronOpen))}>
          <ChevronDown size={14} />
        </span>
      </div>
    );
  },
);
BackgroundProcessChipButton.displayName = "BackgroundProcessChipButton";
