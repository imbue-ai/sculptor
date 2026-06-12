import { Button, Code, Dialog, Flex, Spinner, Text } from "@radix-ui/themes";
import { AlertCircleIcon, CheckCircleIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useRef } from "react";

import { ElementIds } from "~/api";

import styles from "./RepoValidationDialog.module.scss";

type CheckingState = {
  status: "checking";
  repoPath: string;
};

type NotGitRepoState = {
  status: "not-git-repo";
  repoPath: string;
};

type EmptyRepoState = {
  status: "empty-repo";
  repoPath: string;
};

type InitializingState = {
  status: "initializing";
  repoPath: string;
};

type SuccessState = {
  status: "success";
  repoPath: string;
};

type ErrorState = {
  status: "error";
  repoPath: string;
  errorMessage: string;
};

export type RepoValidationState =
  | CheckingState
  | NotGitRepoState
  | EmptyRepoState
  | InitializingState
  | SuccessState
  | ErrorState;

type RepoValidationDialogProps = {
  isOpen: boolean;
  state: RepoValidationState;
  onInitializeGit: () => void;
  onCreateInitialCommit: () => void;
  onCancel: () => void;
};

const isInProgress = (status: RepoValidationState["status"]): boolean =>
  status === "checking" || status === "initializing";

const getDescription = (state: RepoValidationState): string => {
  switch (state.status) {
    case "checking":
      return "Checking your project is a valid repo\u2026";
    case "initializing":
      return "Setting up repository\u2026";
    case "success":
      return "Repository added successfully";
    case "not-git-repo":
    case "empty-repo":
    case "error":
      return "";
  }
};

export const RepoValidationDialog = ({
  isOpen,
  state,
  onInitializeGit,
  onCreateInitialCommit,
  onCancel,
}: RepoValidationDialogProps): ReactElement => {
  const contentRef = useRef<HTMLDivElement>(null);
  const repoName = state.repoPath.split("/").pop() ?? state.repoPath;
  const isLoading = isInProgress(state.status);
  const description = getDescription(state);

  // Make the overlay transparent so the parent AddRepoDialog remains visible.
  // Radix renders the overlay as a previous sibling of content inside the portal,
  // and CSS cannot select a previous sibling, so we must style it imperatively.
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    // Walk siblings to find the overlay — more resilient than assuming it's the
    // immediate previous sibling, in case Radix changes the portal structure.
    const parent = el.parentElement;
    if (!parent) return;
    const overlay = parent.querySelector<HTMLElement>(":scope > .rt-DialogOverlay");
    if (overlay) {
      overlay.style.backgroundColor = "transparent";
    }
  }, [isOpen]);

  const renderTitleIcon = (): ReactNode => {
    if (isLoading) {
      return <Spinner size="2" />;
    }

    if (state.status === "success") {
      return <CheckCircleIcon size={18} className={styles.successIcon} />;
    }

    if (state.status === "error") {
      return <AlertCircleIcon size={18} className={styles.errorIcon} />;
    }
    return <AlertCircleIcon size={18} className={styles.warningIcon} />;
  };

  return (
    <Dialog.Root open={isOpen}>
      <Dialog.Content ref={contentRef} maxWidth="420px" data-testid={ElementIds.PROJECT_GIT_INIT_DIALOG}>
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

        {state.status === "not-git-repo" && (
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

        {state.status === "empty-repo" && (
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

        {state.status === "error" && (
          <Flex direction="column" gap="3" mt="3">
            <Text size="2" className={styles.messageBox}>
              {state.errorMessage}
            </Text>
            <Flex gap="3" justify="end">
              <Button variant="soft" color="gray" onClick={onCancel}>
                Close
              </Button>
            </Flex>
          </Flex>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};
