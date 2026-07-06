import { ContextMenu, DropdownMenu, Flex, IconButton, Popover, Spinner, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { Check, ChevronDown, ChevronUp, CopyIcon, GitMergeIcon, Info, PlusIcon, TriangleAlert } from "lucide-react";
import { posthog } from "posthog-js";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { PrStatusInfo } from "../../../api";
import { ElementIds } from "../../../api";
import { chatActionsAtom } from "../../../common/state/atoms/chatActions.ts";
import { prStatusAtomFamily } from "../../../common/state/atoms/prStatus.ts";
import { prCreationPromptAtom } from "../../../common/state/atoms/userConfig.ts";
import type { GitProvider } from "../../../common/state/hooks/useGitProvider.ts";
import styles from "./PrButton.module.scss";
import { PrDetailDropdown } from "./PrDetailDropdown.tsx";
import { PrPromptDialog } from "./PrPromptDialog.tsx";

export type PrErrorCategory =
  | "cli_missing"
  | "not_authenticated"
  | "no_access"
  | "network_error"
  | "rate_limited"
  | "transient";

export type EffectiveError = {
  category: PrErrorCategory;
  message: string | null;
};

type ErrorContent = {
  title: string;
  description: string;
  command: string | null;
};

const ERROR_CONTENT: Record<string, ErrorContent> = {
  cli_missing: {
    title: "GitHub CLI not installed",
    description: "Install gh to create and manage pull requests.",
    command: "brew install gh",
  },
  not_authenticated: {
    title: "GitHub authentication required",
    description: "Sign in to enable pull requests.",
    command: "gh auth login",
  },
  no_access: {
    title: "Repository access denied",
    description: "Can't access this repository. Re-authenticate, or check your access with your admin.",
    command: "gh auth login --scopes repo",
  },
  network_error: {
    title: "Can't connect to GitHub",
    description: "DNS resolution failed. Check your network connection.",
    command: null,
  },
  rate_limited: {
    title: "Rate limited by GitHub",
    description: "Too many API requests. Status updates are paused and will resume automatically.",
    command: null,
  },
  transient: {
    title: "Failed to fetch PR status",
    description: "Something went wrong. Will retry automatically.",
    command: null,
  },
};

const USER_ACTIONABLE_ERRORS = new Set<PrErrorCategory>([
  "cli_missing",
  "not_authenticated",
  "no_access",
  "network_error",
]);

const getErrorContent = (category: PrErrorCategory): ErrorContent => {
  return (
    ERROR_CONTENT[category] ?? {
      title: "Failed to fetch PR status",
      description: "Something went wrong. Will retry automatically.",
      command: null,
    }
  );
};

type PrButtonProps = {
  workspaceId: string;
  targetBranch: string | null | undefined;
  hideCreateAction?: boolean;
  gitProvider: GitProvider;
  onSwitchTarget?: (newTarget: string) => void;
};

type CreatePrButtonProps = {
  targetBranch: string;
  gitProvider: GitProvider;
};

const CreatePrButton = ({ targetBranch, gitProvider }: CreatePrButtonProps): ReactElement => {
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const chatActions = useAtomValue(chatActionsAtom);
  const [isPromptDialogOpen, setIsPromptDialogOpen] = useState(false);

  const handleClick = (): void => {
    const message = `${prCreationPrompt}\n\nTarget the pull request against \`${targetBranch}\`.`;
    posthog.capture("pr.create_initiated", {
      git_provider: gitProvider,
      // The branch name is user-entered text (it can encode feature/ticket/
      // customer names), so it is deliberately not recorded.
    });
    chatActions.sendMessage?.(message);
  };

  return (
    <>
      <ContextMenu.Root>
        <ContextMenu.Trigger>
          <button
            type="button"
            className={styles.createButton}
            onClick={handleClick}
            data-testid={ElementIds.PR_BUTTON_CREATE}
          >
            <PlusIcon size={12} className={styles.plusIcon} />
            <Text size="1">Create PR</Text>
          </button>
        </ContextMenu.Trigger>
        <ContextMenu.Content size="1">
          <ContextMenu.Item onSelect={() => setIsPromptDialogOpen(true)}>Edit prompt...</ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Root>
      <PrPromptDialog open={isPromptDialogOpen} onOpenChange={setIsPromptDialogOpen} />
    </>
  );
};

const getPipelineDotClass = (status: string | null | undefined): string => {
  switch (status) {
    case "running":
      return styles.dotRunning;
    case "passed":
      return styles.dotPassed;
    case "failed":
      return styles.dotFailed;
    case null:
    case undefined:
    default:
      return styles.dotMuted;
  }
};

const getPipelineTooltip = (status: string | null | undefined): string => {
  switch (status) {
    case "running":
      return "Pipeline running";
    case "passed":
      return "Pipeline passed";
    case "failed":
      return "Pipeline failed";
    case null:
    case undefined:
    default:
      return "No pipeline";
  }
};

const getReviewDotClass = (prStatus: PrStatusInfo): string => {
  if (!prStatus.approvals || prStatus.approvals.length === 0) {
    return styles.dotMuted;
  }

  if (prStatus.approvals.every((a) => a.approved)) {
    return styles.dotApproved;
  }

  return styles.dotPending;
};

const getReviewTooltip = (prStatus: PrStatusInfo): string => {
  if (!prStatus.approvals || prStatus.approvals.length === 0) {
    return "No reviewers";
  }

  if (prStatus.approvals.every((a) => a.approved)) {
    return "Approved";
  }

  return "Review pending";
};

type OpenPrButtonProps = {
  prStatus: PrStatusInfo;
  isDropdownOpen: boolean;
  gitProvider: GitProvider;
};

const OpenPrButton = ({ prStatus, isDropdownOpen, gitProvider }: OpenPrButtonProps): ReactElement => {
  const handleOpenUrl = (): void => {
    if (prStatus.prWebUrl) {
      posthog.capture("pr.opened_in_browser", {
        git_provider: gitProvider,
        pr_state: "open",
      });
      window.open(prStatus.prWebUrl, "_blank");
    }
  };

  return (
    <div className={styles.openButton}>
      <Tooltip content={`Open #${prStatus.prIid} in GitHub`}>
        <button
          type="button"
          className={styles.prNumberArea}
          onClick={handleOpenUrl}
          data-testid={ElementIds.PR_BUTTON_OPEN}
        >
          <Text size="1">PR #{prStatus.prIid}</Text>
          <Tooltip content={getPipelineTooltip(prStatus.pipelineStatus)}>
            <span className={`${styles.statusDot} ${getPipelineDotClass(prStatus.pipelineStatus)}`} />
          </Tooltip>
          <Tooltip content={getReviewTooltip(prStatus)}>
            <span className={`${styles.statusDot} ${getReviewDotClass(prStatus)}`} />
          </Tooltip>
        </button>
      </Tooltip>
      <Popover.Trigger>
        <button type="button" className={styles.chevronArea} data-testid={ElementIds.PR_BUTTON_CHEVRON}>
          {isDropdownOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </Popover.Trigger>
    </div>
  );
};

type MergedPrButtonProps = {
  prStatus: PrStatusInfo;
  gitProvider: GitProvider;
};

const MergedPrButton = ({ prStatus, gitProvider }: MergedPrButtonProps): ReactElement => {
  const isClosed = prStatus.prState === "closed";
  const stateLabel = isClosed ? "closed" : "merged";
  const tooltipContent = isClosed
    ? `#${prStatus.prIid} was closed without merging — open in GitHub`
    : `Open #${prStatus.prIid} in GitHub`;

  const handleOpenUrl = (): void => {
    if (prStatus.prWebUrl) {
      posthog.capture("pr.opened_in_browser", {
        git_provider: gitProvider,
        pr_state: "merged",
      });
      window.open(prStatus.prWebUrl, "_blank");
    }
  };

  return (
    <Tooltip content={tooltipContent}>
      <button
        type="button"
        className={styles.mergedButton}
        onClick={handleOpenUrl}
        data-testid={ElementIds.PR_BUTTON_MERGED}
        data-pr-state={prStatus.prState}
      >
        <GitMergeIcon size={12} className={styles.mergeIcon} />
        <Text size="1">PR #{prStatus.prIid}</Text>
        <Text size="1" className={styles.mergedLabel}>
          {stateLabel}
        </Text>
      </button>
    </Tooltip>
  );
};

const LoadingPrButton = (): ReactElement => (
  <div className={styles.loadingButton}>
    <Spinner size="1" />
    <Text size="1">Checking PR...</Text>
  </div>
);

type ErrorPrButtonProps = {
  error: EffectiveError;
};

const ErrorPrButton = ({ error }: ErrorPrButtonProps): ReactElement => {
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Prevent setState-on-unmount from the "Copied!" timer
  useEffect(() => {
    return (): void => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const isUserActionable = USER_ACTIONABLE_ERRORS.has(error.category);
  const content = getErrorContent(error.category);

  const handleCopyCommand = useCallback(async (): Promise<void> => {
    if (!content.command) return;
    try {
      await navigator.clipboard.writeText(content.command);
      setIsCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setIsCopied(false), 2000);
    } catch {
      // Clipboard write failed silently
    }
  }, [content.command]);

  return (
    <Popover.Root open={isPopoverOpen} onOpenChange={setIsPopoverOpen}>
      <div className={styles.errorSplitButton}>
        <Popover.Trigger>
          <span
            role="button"
            tabIndex={0}
            className={styles.errorMainArea}
            data-testid={ElementIds.PR_BUTTON_ERROR}
            data-error-actionable={isUserActionable ? "true" : "false"}
          >
            {isUserActionable ? (
              <TriangleAlert size={12} className={styles.warningIcon} />
            ) : (
              <Info size={12} className={styles.infoIcon} />
            )}
            <Text size="1">Create PR</Text>
          </span>
        </Popover.Trigger>
        <Popover.Trigger>
          <span role="button" tabIndex={0} className={styles.errorChevronArea}>
            {isPopoverOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </span>
        </Popover.Trigger>
      </div>
      <Popover.Content
        align="end"
        sideOffset={5}
        onOpenAutoFocus={(e) => e.preventDefault()}
        className={styles.errorPopoverContent}
        data-testid={ElementIds.PR_BUTTON_ERROR_POPOVER}
      >
        <Flex direction="column" gap="2">
          <Text size="2" weight="medium">
            {content.title}
          </Text>
          <Text size="1" color="gray">
            {content.description}
          </Text>
          {error.message && (
            <details className={styles.errorDetails}>
              <summary data-testid={ElementIds.PR_BUTTON_ERROR_DETAILS}>
                <Text size="1" color="gray">
                  Details
                </Text>
              </summary>
              <Text size="1" color="gray" className={styles.errorMessageDetail}>
                {error.message}
              </Text>
            </details>
          )}
          {content.command !== null && (
            <Flex align="center" gap="2" className={styles.errorCommand}>
              <Text size="1" className={styles.errorCommandText}>
                {content.command}
              </Text>
              <IconButton variant="ghost" size="1" onClick={handleCopyCommand} className={styles.errorCopyButton}>
                {isCopied ? <Check size={12} /> : <CopyIcon size={12} />}
              </IconButton>
            </Flex>
          )}
        </Flex>
      </Popover.Content>
    </Popover.Root>
  );
};

type AssignPrButtonProps = {
  prStatus: PrStatusInfo;
  targetBranch: string;
  gitProvider: GitProvider;
  onSwitchTarget?: (newTarget: string) => void;
};

const AssignPrButton = ({ prStatus, targetBranch, gitProvider, onSwitchTarget }: AssignPrButtonProps): ReactElement => {
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const chatActions = useAtomValue(chatActionsAtom);

  const handleCreate = (): void => {
    const message = `${prCreationPrompt}\n\nTarget the pull request against \`${targetBranch}\`.`;
    posthog.capture("pr.create_initiated", {
      git_provider: gitProvider,
      // The branch name is user-entered text (it can encode feature/ticket/
      // customer names), so it is deliberately not recorded.
    });
    chatActions.sendMessage?.(message);
  };

  const handleSwitchTarget = (): void => {
    if (prStatus.mismatchedPrTargetBranch && onSwitchTarget) {
      onSwitchTarget(prStatus.mismatchedPrTargetBranch);
    }
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <div className={styles.assignButton} data-testid={ElementIds.PR_BUTTON_ASSIGN}>
          <span className={styles.assignMainArea}>
            <GitMergeIcon size={12} className={styles.assignMergeIcon} />
            <Text size="1">Assign PR</Text>
          </span>
        </div>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content size="1" align="end">
        <DropdownMenu.Item onSelect={handleCreate}>
          <PlusIcon size={12} />
          Create PR → <span className={styles.monoBranch}>{targetBranch}</span>
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Item onSelect={handleSwitchTarget}>
          <GitMergeIcon size={12} />
          PR #{prStatus.mismatchedPrIid} exists → switch target to{" "}
          <span className={styles.monoBranch}>{prStatus.mismatchedPrTargetBranch}</span>
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};

export const PrButton = ({
  workspaceId,
  targetBranch,
  hideCreateAction,
  gitProvider,
  onSwitchTarget,
}: PrButtonProps): ReactElement | null => {
  const prStatus = useAtomValue(prStatusAtomFamily(workspaceId));
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const effectiveError: EffectiveError | null = prStatus?.errorCategory
    ? {
        category: prStatus.errorCategory as PrErrorCategory,
        message: prStatus.errorMessage ?? null,
      }
    : null;

  // No status yet — still loading (waiting for first backend poll)
  if (!prStatus) {
    if (hideCreateAction) {
      return null;
    }
    return <LoadingPrButton />;
  }

  if (effectiveError) {
    if (hideCreateAction) {
      return null;
    }
    return <ErrorPrButton error={effectiveError} />;
  }

  if (prStatus.prState === "none") {
    if (hideCreateAction) {
      return null;
    }

    const targetBare = (targetBranch ?? "").replace(/^[^/]+\//, "");
    const isMismatchRelevant =
      prStatus.mismatchedPrIid != null &&
      prStatus.mismatchedPrTargetBranch != null &&
      prStatus.mismatchedPrTargetBranch !== targetBare;
    if (isMismatchRelevant) {
      return (
        <AssignPrButton
          prStatus={prStatus}
          targetBranch={targetBranch ?? "origin/main"}
          gitProvider={gitProvider}
          onSwitchTarget={onSwitchTarget}
        />
      );
    }
    return <CreatePrButton targetBranch={targetBranch ?? "origin/main"} gitProvider={gitProvider} />;
  }

  if (prStatus.prState === "open") {
    return (
      <Popover.Root open={isDropdownOpen} onOpenChange={setIsDropdownOpen}>
        <OpenPrButton prStatus={prStatus} isDropdownOpen={isDropdownOpen} gitProvider={gitProvider} />
        <Popover.Content align="end" sideOffset={5} onOpenAutoFocus={(e) => e.preventDefault()}>
          <PrDetailDropdown prStatus={prStatus} />
        </Popover.Content>
      </Popover.Root>
    );
  }

  if (prStatus.prState === "merged" || prStatus.prState === "closed") {
    return <MergedPrButton prStatus={prStatus} gitProvider={gitProvider} />;
  }

  return null;
};
