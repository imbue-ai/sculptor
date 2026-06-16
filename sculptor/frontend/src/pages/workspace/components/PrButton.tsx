import { Flex, IconButton, Popover, Spinner, Text, Tooltip } from "@radix-ui/themes";
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
import styles from "./PrButton.module.scss";

export type GitProvider = "gitlab" | "github" | null;

export type PrErrorCategory =
  | "cli_missing"
  | "not_authenticated"
  | "no_access"
  | "network_error"
  | "rate_limited"
  | "transient";

export type EffectiveError = {
  category: PrErrorCategory;
  provider: "gitlab" | "github" | null;
  message: string | null;
};

type ErrorContent = {
  title: string;
  description: string;
  command: string | null;
};

const ERROR_CONTENT: Record<string, Record<string, ErrorContent>> = {
  cli_missing: {
    gitlab: {
      title: "GitLab CLI not installed",
      description: "Install glab to create and manage merge requests.",
      command: "brew install glab",
    },
    github: {
      title: "GitHub CLI not installed",
      description: "Install gh to create and manage pull requests.",
      command: "brew install gh",
    },
  },
  not_authenticated: {
    gitlab: {
      title: "GitLab authentication required",
      description: "Sign in to enable merge requests.",
      command: "glab auth login",
    },
    github: {
      title: "GitHub authentication required",
      description: "Sign in to enable pull requests.",
      command: "gh auth login",
    },
  },
  no_access: {
    gitlab: {
      title: "Repository access denied",
      description: "Can't access this repository. Re-authenticate, or check your access with your admin.",
      command: "glab auth login --scopes api,write_repository",
    },
    github: {
      title: "Repository access denied",
      description: "Can't access this repository. Re-authenticate, or check your access with your admin.",
      command: "gh auth login --scopes repo",
    },
  },
  network_error: {
    gitlab: {
      title: "Can't connect to GitLab",
      description: "DNS resolution failed. Check your network connection.",
      command: null,
    },
    github: {
      title: "Can't connect to GitHub",
      description: "DNS resolution failed. Check your network connection.",
      command: null,
    },
  },
  rate_limited: {
    gitlab: {
      title: "Rate limited by GitLab",
      description: "Too many API requests. Status updates are paused and will resume automatically.",
      command: null,
    },
    github: {
      title: "Rate limited by GitHub",
      description: "Too many API requests. Status updates are paused and will resume automatically.",
      command: null,
    },
  },
  transient: {
    gitlab: {
      title: "Failed to fetch MR status",
      description: "Something went wrong. Will retry automatically.",
      command: null,
    },
    github: {
      title: "Failed to fetch PR status",
      description: "Something went wrong. Will retry automatically.",
      command: null,
    },
  },
};

const USER_ACTIONABLE_ERRORS = new Set<PrErrorCategory>([
  "cli_missing",
  "not_authenticated",
  "no_access",
  "network_error",
]);

const getErrorContent = (category: PrErrorCategory, provider: "gitlab" | "github" | null): ErrorContent => {
  const providerKey = provider ?? "github";
  return (
    ERROR_CONTENT[category]?.[providerKey] ?? {
      title: providerKey === "gitlab" ? "Failed to fetch MR status" : "Failed to fetch PR status",
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

// No dropdown in any state (REQ-TOPBAR-7): the create button is a single
// action with no "edit prompt" chevron.
const CreatePrButton = ({ targetBranch, gitProvider }: CreatePrButtonProps): ReactElement => {
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const chatActions = useAtomValue(chatActionsAtom);

  const isGitLab = gitProvider === "gitlab";
  const buttonLabel = isGitLab ? "Create MR" : "Create PR";

  const handleClick = (): void => {
    const prTerm = isGitLab ? "merge request" : "pull request";
    const message = `${prCreationPrompt}\n\nTarget the ${prTerm} against \`${targetBranch}\`.`;
    posthog.capture("pr.create_initiated", {
      git_provider: gitProvider,
      // The branch name is user-entered text (it can encode feature/ticket/
      // customer names), so it is deliberately not recorded.
    });
    chatActions.sendMessage?.(message);
  };

  return (
    <div className={styles.createSplitButton}>
      <button
        type="button"
        className={styles.createMainArea}
        onClick={handleClick}
        data-testid={ElementIds.PR_BUTTON_CREATE}
      >
        <PlusIcon size={12} className={styles.plusIcon} />
        <Text size="1">{buttonLabel}</Text>
      </button>
    </div>
  );
};

// Open PR/MR → a plain link to the PR, no detail dropdown (REQ-TOPBAR-7).
type OpenPrLinkProps = {
  prStatus: PrStatusInfo;
  gitProvider: GitProvider;
};

const OpenPrLink = ({ prStatus, gitProvider }: OpenPrLinkProps): ReactElement => {
  const isGitHub = gitProvider === "github";
  const prefix = isGitHub ? "#" : "!";
  const label = isGitHub ? "PR" : "MR";
  const providerName = isGitHub ? "GitHub" : "GitLab";

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
    <Tooltip content={`Open ${prefix}${prStatus.prIid} in ${providerName}`}>
      <button
        type="button"
        className={styles.mergedButton}
        data-pr-state="open"
        onClick={handleOpenUrl}
        data-testid={ElementIds.PR_BUTTON_OPEN}
      >
        <Text size="1">
          {label} {prefix}
          {prStatus.prIid}
        </Text>
      </button>
    </Tooltip>
  );
};

type MergedPrButtonProps = {
  prStatus: PrStatusInfo;
  gitProvider: GitProvider;
};

const MergedPrButton = ({ prStatus, gitProvider }: MergedPrButtonProps): ReactElement => {
  const isGitHub = gitProvider === "github";
  const prefix = isGitHub ? "#" : "!";
  const label = isGitHub ? "PR" : "MR";
  const providerName = isGitHub ? "GitHub" : "GitLab";
  const isClosed = prStatus.prState === "closed";
  const stateLabel = isClosed ? "closed" : "merged";
  const tooltipContent = isClosed
    ? `${prefix}${prStatus.prIid} was closed without merging — open in ${providerName}`
    : `Open ${prefix}${prStatus.prIid} in ${providerName}`;

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
        <Text size="1">
          {label} {prefix}
          {prStatus.prIid}
        </Text>
        <Text size="1" className={styles.mergedLabel}>
          {stateLabel}
        </Text>
      </button>
    </Tooltip>
  );
};

const LoadingPrButton = ({ gitProvider }: { gitProvider: GitProvider }): ReactElement => (
  <div className={styles.loadingButton}>
    <Spinner size="1" />
    <Text size="1">Checking {gitProvider === "gitlab" ? "MR" : "PR"}...</Text>
  </div>
);

type ErrorPrButtonProps = {
  error: EffectiveError;
  gitProvider: GitProvider;
};

const ErrorPrButton = ({ error, gitProvider }: ErrorPrButtonProps): ReactElement => {
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
  const content = getErrorContent(error.category, error.provider ?? gitProvider);
  const isGitLab = (error.provider ?? gitProvider) === "gitlab";
  const buttonLabel = isGitLab ? "Create MR" : "Create PR";

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
            <Text size="1">{buttonLabel}</Text>
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

export const PrButton = ({
  workspaceId,
  targetBranch,
  hideCreateAction,
  gitProvider,
}: PrButtonProps): ReactElement | null => {
  const prStatus = useAtomValue(prStatusAtomFamily(workspaceId));

  const effectiveError: EffectiveError | null = prStatus?.errorCategory
    ? {
        category: prStatus.errorCategory as PrErrorCategory,
        provider: prStatus.errorProvider ?? null,
        message: prStatus.errorMessage ?? null,
      }
    : null;

  // No status yet — still loading (waiting for first backend poll)
  if (!prStatus) {
    if (hideCreateAction) {
      return null;
    }
    return <LoadingPrButton gitProvider={gitProvider} />;
  }

  if (effectiveError) {
    if (hideCreateAction) {
      return null;
    }
    return <ErrorPrButton error={effectiveError} gitProvider={gitProvider} />;
  }

  if (prStatus.prState === "none") {
    if (hideCreateAction) {
      return null;
    }
    // No dropdown in any state (REQ-TOPBAR-7): even the target-mismatch case
    // just offers a plain create action.
    return <CreatePrButton targetBranch={targetBranch ?? "origin/main"} gitProvider={gitProvider} />;
  }

  if (prStatus.prState === "open") {
    return <OpenPrLink prStatus={prStatus} gitProvider={gitProvider} />;
  }

  if (prStatus.prState === "merged" || prStatus.prState === "closed") {
    return <MergedPrButton prStatus={prStatus} gitProvider={gitProvider} />;
  }

  return null;
};
