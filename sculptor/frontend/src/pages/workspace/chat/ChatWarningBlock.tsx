import { Badge } from "@radix-ui/themes";
import { ChevronRightIcon } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useState } from "react";

import type { WarningBlock } from "~/api";

import styles from "./ChatView.module.scss";

export const ChatWarningBlock = ({ block }: { block: WarningBlock }): ReactElement => {
  const [isExpanded, setIsExpanded] = useState(false);
  const warningLabel = block.warningType ? block.warningType.split(".").pop() : "Warning";
  const hasContent = block.traceback !== null && block.traceback.trim().length > 0;

  const handleToggle = (): void => setIsExpanded((prev) => !prev);
  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleToggle();
    }
  };

  return (
    <div className={styles.warningBlock}>
      <div
        className={`${styles.warningHeader} ${hasContent ? styles.warningHeaderClickable : ""}`}
        onClick={hasContent ? handleToggle : undefined}
        role={hasContent ? "button" : undefined}
        tabIndex={hasContent ? 0 : undefined}
        aria-expanded={hasContent ? isExpanded : undefined}
        onKeyDown={hasContent ? handleKeyDown : undefined}
      >
        {hasContent && (
          <ChevronRightIcon size={12} className={isExpanded ? styles.chevronOpen : styles.chevronClosed} />
        )}
        <Badge color="orange" size="1" variant="soft">
          {warningLabel}
        </Badge>
        <span className={styles.warningMessage}>{block.message || "Unknown warning"}</span>
      </div>
      {isExpanded && hasContent && (
        <div className={styles.tracebackScroll}>
          <pre className={styles.errorTraceback}>{block.traceback}</pre>
        </div>
      )}
    </div>
  );
};
