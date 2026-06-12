import { Button, Tooltip } from "@radix-ui/themes";
import { ArrowDownIcon } from "lucide-react";
import type { ReactElement, RefObject } from "react";
import { useEffect, useRef } from "react";

import { ElementIds } from "~/api";

import styles from "./JumpToBottomButton.module.scss";

type JumpToBottomButtonProps = {
  isVisible: boolean;
  label: "jump" | "new";
  onClick: () => void;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
};

export const JumpToBottomButton = ({
  isVisible,
  label,
  onClick,
  scrollContainerRef,
}: JumpToBottomButtonProps): ReactElement => {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const wasVisible = useRef(isVisible);

  // Focus management: move focus to scroll container when button disappears while focused
  useEffect(() => {
    if (wasVisible.current && !isVisible) {
      if (document.activeElement === buttonRef.current) {
        scrollContainerRef.current?.focus();
      }
    }
    wasVisible.current = isVisible;
  }, [isVisible, scrollContainerRef]);

  const ariaLabel = label === "new" ? "Jump to bottom — new activity" : "Jump to bottom";
  const tooltipContent = "Jump to bottom";

  return (
    <div
      className={`${styles.wrapper} ${isVisible ? styles.visible : styles.hidden}`}
      aria-hidden={!isVisible}
      data-testid={ElementIds.ALPHA_JUMP_TO_BOTTOM_WRAPPER}
    >
      <Tooltip content={tooltipContent}>
        <Button
          ref={buttonRef}
          variant="outline"
          color="gray"
          size="1"
          className={styles.button}
          onClick={onClick}
          aria-label={ariaLabel}
          data-testid={ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON}
          tabIndex={isVisible ? 0 : -1}
        >
          {label === "new" ? <span className={styles.activityLabel}>New activity</span> : "Jump"}
          <ArrowDownIcon className={styles.icon} size={12} />
        </Button>
      </Tooltip>
    </div>
  );
};
