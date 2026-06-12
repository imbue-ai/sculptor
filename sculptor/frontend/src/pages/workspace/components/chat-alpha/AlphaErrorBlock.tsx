import { CheckCircledIcon } from "@radix-ui/react-icons";
import { Badge, Button, Flex, Link, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { ChevronRightIcon, RefreshCw } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import type { ErrorBlock } from "~/api";
import { ElementIds, TaskStatus } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";

import styles from "./AlphaChatView.module.scss";

export const AlphaErrorBlock = ({
  block,
  isLastMessage,
  taskStatus,
  onRetryRequest,
}: {
  block: ErrorBlock;
  isLastMessage: boolean;
  taskStatus: TaskStatus;
  onRetryRequest?: () => void;
}): ReactElement => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const isClaudeInstalled = dependenciesStatus?.claude?.installed ?? false;
  const [isExpanded, setIsExpanded] = useState(false);
  const [hasRetried, setHasRetried] = useState(false);
  const openSettings = useOpenSettings();
  const isClaudeBinaryNotFound = block.errorType?.endsWith("ClaudeBinaryNotFoundError") ?? false;
  const errorLabel = block.errorType ? block.errorType.split(".").pop() : "Request Failed";
  const showRetry = !isClaudeBinaryNotFound && isLastMessage && taskStatus !== TaskStatus.ERROR && onRetryRequest;

  if (isClaudeBinaryNotFound) {
    return (
      <>
        <div className={styles.errorBlock} data-testid={ElementIds.ERROR_BLOCK}>
          <div className={styles.errorHeader}>
            <Badge color={isClaudeInstalled ? "orange" : "red"} size="1" variant="soft">
              Claude Not Available
            </Badge>
            <span className={styles.errorMessage}>
              {block.message || "Claude binary not found or is invalid."}{" "}
              <Link onClick={() => openSettings("DEPENDENCIES")} style={{ cursor: "pointer" }}>
                Go to Settings
              </Link>
            </span>
          </div>
        </div>
        {isClaudeInstalled && (
          <Flex align="center" gap="1" style={{ paddingTop: "var(--space-1)" }}>
            <CheckCircledIcon color="var(--green-9)" />
            <Badge color="green" size="1" variant="soft">
              Claude installed
            </Badge>
          </Flex>
        )}
      </>
    );
  }

  return (
    <div className={styles.errorBlock} data-testid={ElementIds.ERROR_BLOCK}>
      <div
        className={styles.errorHeader}
        onClick={(): void => setIsExpanded((prev) => !prev)}
        role="button"
        tabIndex={0}
        onKeyDown={(e): void => {
          if (e.key === "Enter" || e.key === " ") setIsExpanded((prev) => !prev);
        }}
      >
        <ChevronRightIcon size={12} className={isExpanded ? styles.chevronOpen : styles.chevronClosed} />
        <Badge color="red" size="1" variant="soft">
          {errorLabel}
        </Badge>
        <span className={styles.errorMessage}>{block.message || "Unknown error"}</span>
      </div>
      {isExpanded && block.traceback && (
        <div className={styles.tracebackScroll}>
          <pre className={styles.errorTraceback}>{block.traceback}</pre>
        </div>
      )}
      {showRetry && (
        <div style={{ paddingTop: "var(--space-1)" }}>
          {hasRetried ? (
            <Tooltip content="This request has already been retried.">
              <span>
                <Button size="1" variant="solid" color="red" disabled data-testid={ElementIds.ERROR_BLOCK_RETRY_BUTTON}>
                  Retry Request <RefreshCw size={14} />
                </Button>
              </span>
            </Tooltip>
          ) : (
            <Button
              size="1"
              variant="solid"
              color="red"
              data-testid={ElementIds.ERROR_BLOCK_RETRY_BUTTON}
              onClick={(e): void => {
                e.stopPropagation();
                setHasRetried(true);
                onRetryRequest();
              }}
            >
              Retry Request <RefreshCw size={14} />
            </Button>
          )}
        </div>
      )}
    </div>
  );
};
