import { Button, Code, Dialog, Flex, IconButton, Spinner, Text } from "@radix-ui/themes";
import { AlertCircleIcon, Check, CopyIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import type { AddRepoPhase } from "~/components/addRepo/hooks/useAddRepo.tsx";

import styles from "./RepoValidationDialog.module.scss";

type RepoValidationViewProps = {
  /**
   * The current phase from useAddRepo. The form, the pre-validation
   * `validating` phase (form stays visible with a spinner button), and the
   * `cloning` phase (dedicated progress card) are handled by the parent, so
   * this view only sees `initializing` and the terminal error states.
   */
  phase: Exclude<AddRepoPhase, { type: "form" | "validating" | "cloning" }>;
  onInitializeGit: () => void;
  onCreateInitialCommit: () => void;
  onCancel: () => void;
  /** Triggered by the "Add as local folder" CTA in the clone-failed phase. */
  onOpenLocal?: (path: string) => void;
};

const getDescription = (phase: RepoValidationViewProps["phase"]): string => {
  switch (phase.type) {
    case "initializing":
      return "Setting up repository…";
    case "not-git-repo":
    case "empty-repo":
    case "error":
    case "clone-failed":
      return "";
  }
};

export const RepoValidationView = ({
  phase,
  onInitializeGit,
  onCreateInitialCommit,
  onCancel,
  onOpenLocal,
}: RepoValidationViewProps): ReactElement => {
  const repoName = phase.repoPath.split("/").pop() ?? phase.repoPath;
  const description = getDescription(phase);

  const [isPathCopied, setIsPathCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return (): void => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const localPathSuggestion = phase.type === "clone-failed" ? phase.localPathSuggestion : undefined;

  const handleCopyPath = useCallback(async (): Promise<void> => {
    if (!localPathSuggestion) return;
    try {
      await navigator.clipboard.writeText(localPathSuggestion);
      setIsPathCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setIsPathCopied(false), 2000);
    } catch {
      // Clipboard write failed silently
    }
  }, [localPathSuggestion]);

  const renderTitleIcon = (): ReactNode => {
    if (phase.type === "initializing") {
      return <Spinner size="2" />;
    }

    if (phase.type === "error" || phase.type === "clone-failed") {
      return <AlertCircleIcon size={18} className={styles.errorIcon} />;
    }
    return <AlertCircleIcon size={18} className={styles.warningIcon} />;
  };

  return (
    <div data-testid={ElementIds.PROJECT_GIT_INIT_DIALOG}>
      <Dialog.Title>
        <Flex align="center" gap="2">
          {renderTitleIcon()}
          <Text>
            Adding <Code size="4">{repoName}</Code>
          </Text>
        </Flex>
      </Dialog.Title>

      {description && (
        <Dialog.Description size="2" color="gray">
          {description}
        </Dialog.Description>
      )}

      {phase.type === "not-git-repo" && (
        <Flex direction="column" gap="3" mt="3">
          <Text size="2" className={styles.messageBox}>
            This directory is not a git repository. Would you like to initialize it?
          </Text>
          <Flex gap="3" justify="end">
            <Button variant="soft" color="gray" onClick={onCancel} data-testid={ElementIds.PROJECT_GIT_INIT_CANCEL}>
              Cancel
            </Button>
            <Button variant="solid" onClick={onInitializeGit} data-testid={ElementIds.PROJECT_GIT_INIT_CONFIRM}>
              Initialize Git
            </Button>
          </Flex>
        </Flex>
      )}

      {phase.type === "empty-repo" && (
        <Flex direction="column" gap="3" mt="3">
          <Text size="2" className={styles.messageBox}>
            This repository has no commits. Would you like to create an initial commit?
          </Text>
          <Flex gap="3" justify="end">
            <Button variant="soft" color="gray" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              variant="solid"
              onClick={onCreateInitialCommit}
              data-testid={ElementIds.PROJECT_INITIAL_COMMIT_CONFIRM}
            >
              Make Initial Commit
            </Button>
          </Flex>
        </Flex>
      )}

      {phase.type === "error" && (
        <Flex direction="column" gap="3" mt="3">
          <Text size="2" className={styles.messageBox}>
            {phase.errorMessage}
          </Text>
          <Flex gap="3" justify="end">
            <Button variant="soft" color="gray" onClick={onCancel}>
              Close
            </Button>
          </Flex>
        </Flex>
      )}

      {phase.type === "clone-failed" && (
        <Flex direction="column" gap="3" mt="3">
          <Text size="2" className={styles.messageBox} data-testid={ElementIds.ADD_REPO_CLONE_FAILED_MESSAGE}>
            {phase.errorMessage}
          </Text>
          {localPathSuggestion && (
            <Flex align="center" justify="between" gap="2" className={styles.pathBox}>
              <Text size="2" className={styles.pathText} data-testid={ElementIds.ADD_REPO_CLONE_FAILED_PATH}>
                {localPathSuggestion}
              </Text>
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                onClick={handleCopyPath}
                aria-label="Copy path"
                className={styles.pathCopyButton}
                data-testid={ElementIds.ADD_REPO_CLONE_FAILED_COPY}
              >
                {isPathCopied ? <Check size={14} /> : <CopyIcon size={14} />}
              </IconButton>
            </Flex>
          )}
          <Flex gap="3" justify="end">
            <Button variant="soft" color="gray" onClick={onCancel} data-testid={ElementIds.ADD_REPO_CLONE_FAILED_CLOSE}>
              Close
            </Button>
            {localPathSuggestion && onOpenLocal && (
              <Button
                variant="solid"
                onClick={() => onOpenLocal(localPathSuggestion)}
                data-testid={ElementIds.ADD_REPO_CLONE_FAILED_ADD_LOCAL}
              >
                Add as local folder
              </Button>
            )}
          </Flex>
        </Flex>
      )}
    </div>
  );
};
