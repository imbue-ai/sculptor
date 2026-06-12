import { Badge } from "@radix-ui/themes";
import { ChevronRightIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import type { WarningBlock } from "~/api";

import styles from "./AlphaChatView.module.scss";

export const AlphaWarningBlock = ({ block }: { block: WarningBlock }): ReactElement => {
  const [isExpanded, setIsExpanded] = useState(false);
  const warningLabel = block.warningType ? block.warningType.split(".").pop() : "Warning";
  const hasContent = block.traceback && block.traceback.trim().length > 0;

  return (
    <div className={styles.warningBlock}>
      <div
        className={styles.warningHeader}
        onClick={hasContent ? (): void => setIsExpanded((prev) => !prev) : undefined}
        role={hasContent ? "button" : undefined}
        tabIndex={hasContent ? 0 : undefined}
        onKeyDown={
          hasContent
            ? (e): void => {
                if (e.key === "Enter" || e.key === " ") setIsExpanded((prev) => !prev);
              }
            : undefined
        }
        style={{ cursor: hasContent ? "pointer" : "default" }}
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
