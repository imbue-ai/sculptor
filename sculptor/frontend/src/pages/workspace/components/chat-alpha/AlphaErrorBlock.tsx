import { CheckCircledIcon } from "@radix-ui/react-icons";
import { Badge, Button, Flex, Link, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { ChevronRightIcon, RefreshCw } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import type { DependenciesStatus, ErrorBlock } from "~/api";
import { ElementIds, TaskStatus } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";

import styles from "./AlphaChatView.module.scss";

// Agent binaries that, when missing or invalid, surface a friendly "not
// available" block with a link to the settings section where a managed copy can
// be installed, instead of a raw traceback. `getInstalled` reads the live
// dependency status so a green "installed" badge can appear if the binary
// reappears after the error.
type BinaryNotFoundTool = {
  errorSuffix: string;
  name: string;
  settingsSection: string;
  getInstalled: (status: DependenciesStatus) => boolean;
};

const BINARY_NOT_FOUND_TOOLS: ReadonlyArray<BinaryNotFoundTool> = [
  {
    errorSuffix: "ClaudeBinaryNotFoundError",
    name: "Claude",
    settingsSection: "DEPENDENCIES",
    getInstalled: (status: DependenciesStatus): boolean => status.claude.installed,
  },
  {
    errorSuffix: "PiBinaryNotFoundError",
    name: "Pi",
    settingsSection: "PI",
    getInstalled: (status: DependenciesStatus): boolean => status.pi.installed,
  },
];

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
  const [isExpanded, setIsExpanded] = useState(false);
  const [hasRetried, setHasRetried] = useState(false);
  const openSettings = useOpenSettings();
  const binaryNotFoundTool = BINARY_NOT_FOUND_TOOLS.find((tool) => block.errorType?.endsWith(tool.errorSuffix));
  const errorLabel = block.errorType ? block.errorType.split(".").pop() : "Request Failed";
  const showRetry = !binaryNotFoundTool && isLastMessage && taskStatus !== TaskStatus.ERROR && onRetryRequest;

  if (binaryNotFoundTool) {
    const isInstalled = dependenciesStatus ? binaryNotFoundTool.getInstalled(dependenciesStatus) : false;
    return (
      <>
        <div className={styles.errorBlock} data-testid={ElementIds.ERROR_BLOCK}>
          <div className={styles.errorHeader}>
            <Badge color={isInstalled ? "orange" : "red"} size="1" variant="soft">
              {binaryNotFoundTool.name} Not Available
            </Badge>
            <span className={styles.errorMessage}>
              {block.message || `${binaryNotFoundTool.name} binary not found or is invalid.`}{" "}
              <Link onClick={() => openSettings(binaryNotFoundTool.settingsSection)} style={{ cursor: "pointer" }}>
                Go to Settings
              </Link>
            </span>
          </div>
        </div>
        {isInstalled && (
          <Flex align="center" gap="1" style={{ paddingTop: "var(--space-1)" }}>
            <CheckCircledIcon color="var(--green-9)" />
            <Badge color="green" size="1" variant="soft">
              {binaryNotFoundTool.name} installed
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
