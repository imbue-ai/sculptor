import type { ReactElement } from "react";
import { forwardRef } from "react";

import { ElementIds } from "~/api";

import styles from "./AlphaToolPill.module.scss";
import type { PillData } from "./toolPill.types.ts";
import { getToolIcon } from "./toolPillIcons.tsx";

type AlphaToolPillProps = {
  pillData: PillData;
  isOpen: boolean;
  onToggle: () => void;
  onFocus?: () => void;
  tabIndex?: 0 | -1;
};

export const AlphaToolPill = forwardRef<HTMLButtonElement, AlphaToolPillProps>(
  ({ pillData, isOpen, onToggle, onFocus, tabIndex }, ref): ReactElement => {
    const { state, label } = pillData;
    // Command-style tools (Bash, Monitor) and Workflow share the pulsing-dot
    // executing affordance — they're the long-running tools whose duration is
    // meaningful enough to surface visually.
    const isCommandStyleTool = label === "Bash" || label === "Monitor" || label === "Workflow";
    const isExecuting = state === "initializing";
    const Icon = getToolIcon(label);

    const classNames = [styles.pill];
    if (isOpen) classNames.push(styles.pillOpen);
    if (state === "error") classNames.push(styles.pillError);

    // Bash pills get a unique testid so integration tests can locate them
    // separately from non-bash tool pills.
    const testId = label === "Bash" ? ElementIds.ALPHA_CHAT_BASH_BLOCK : ElementIds.ALPHA_CHAT_TOOL_PILL;

    // While a command-style tool is executing, the tool icon is replaced by
    // a pulsing status dot. Once it finishes (completed or error) the Lucide
    // icon comes back. The dot's margin matches the icon's width so the
    // label position is identical across the swap.
    const isShowingStatusDot = isCommandStyleTool && isExecuting;

    return (
      <button
        ref={ref}
        className={classNames.join(" ")}
        onClick={onToggle}
        onFocus={onFocus}
        tabIndex={tabIndex}
        data-testid={testId}
        data-tool-state={state}
      >
        {isShowingStatusDot ? (
          <span className={`${styles.statusDot} ${styles.statusDotPulsing}`} aria-label="executing" />
        ) : (
          <Icon className={styles.pillIcon} aria-hidden="true" />
        )}
        <span>{label}</span>
      </button>
    );
  },
);

AlphaToolPill.displayName = "AlphaToolPill";
