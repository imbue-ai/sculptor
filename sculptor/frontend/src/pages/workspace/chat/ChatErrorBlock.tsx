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

import styles from "./ChatView.module.scss";

// Tools that, when missing, invalid or otherwise unusable, surface a friendly
// "not available" block with the reason and a link to the settings section
// where they are fixed, instead of a raw traceback. `getInstalled` reads the
// live dependency status so a green badge can appear if the tool becomes usable
// after the error; `recoveredLabel` is what that badge says.
type UnavailableTool = {
  errorSuffix: string;
  name: string;
  settingsSection: string;
  recoveredLabel: string;
  getInstalled: (status: DependenciesStatus) => boolean;
};

const UNAVAILABLE_TOOLS: ReadonlyArray<UnavailableTool> = [
  {
    errorSuffix: "ClaudeBinaryNotFoundError",
    name: "Claude",
    settingsSection: "DEPENDENCIES",
    recoveredLabel: "installed",
    getInstalled: (status: DependenciesStatus): boolean => status.claude.installed,
  },
  {
    errorSuffix: "PiBinaryNotFoundError",
    name: "Pi",
    settingsSection: "PI",
    recoveredLabel: "installed",
    getInstalled: (status: DependenciesStatus): boolean => status.pi.installed,
  },
  // A jj workspace's agent stops, saying why, before running jj when jj cannot be used.
  {
    errorSuffix: "JjUnavailableError",
    name: "jj",
    settingsSection: "JJ",
    recoveredLabel: "available",
    getInstalled: (status: DependenciesStatus): boolean => status.jjReadiness.blocker === null,
  },
];

export const ChatErrorBlock = ({
  block,
  isLastMessage,
  agentStatus,
  onRetryRequest,
}: {
  block: ErrorBlock;
  isLastMessage: boolean;
  agentStatus: TaskStatus;
  onRetryRequest?: () => void;
}): ReactElement => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const [isExpanded, setIsExpanded] = useState(false);
  const [hasRetried, setHasRetried] = useState(false);
  const openSettings = useOpenSettings();
  const unavailableTool = UNAVAILABLE_TOOLS.find((tool) => block.errorType?.endsWith(tool.errorSuffix));
  const errorLabel = block.errorType ? block.errorType.split(".").pop() : "Request Failed";
  const showRetry = !unavailableTool && isLastMessage && agentStatus !== TaskStatus.ERROR && onRetryRequest;
  // The pi adapter's provider-auth turn failure leads with this phrasing
  // (humanize_pi_failure_reason); offer a one-click route to authenticate.
  const isAuthFailure = block.message?.includes("require authentication") ?? false;

  if (unavailableTool) {
    const isInstalled = dependenciesStatus ? unavailableTool.getInstalled(dependenciesStatus) : false;
    return (
      <>
        <div className={styles.errorBlock} data-testid={ElementIds.ERROR_BLOCK}>
          <div className={styles.errorHeader}>
            <Badge color={isInstalled ? "orange" : "red"} size="1" variant="soft">
              {unavailableTool.name} Not Available
            </Badge>
            <span className={styles.errorMessage}>
              {block.message || `${unavailableTool.name} binary not found or is invalid.`}{" "}
              <Link onClick={() => openSettings(unavailableTool.settingsSection)} style={{ cursor: "pointer" }}>
                Go to Settings
              </Link>
            </span>
          </div>
        </div>
        {isInstalled && (
          <Flex align="center" gap="1" style={{ paddingTop: "var(--space-1)" }}>
            <CheckCircledIcon color="var(--green-9)" />
            <Badge color="green" size="1" variant="soft">
              {unavailableTool.name} {unavailableTool.recoveredLabel}
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
      {isAuthFailure && (
        <div style={{ paddingTop: "var(--space-1)" }}>
          <Button
            size="1"
            variant="soft"
            data-testid={ElementIds.PI_ERROR_LOGIN_CTA}
            onClick={(e): void => {
              e.stopPropagation();
              openSettings("PI");
            }}
          >
            Open pi login
          </Button>
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
