import { Button, Flex, Tooltip } from "@radix-ui/themes";
import type { ReactElement, ReactNode, RefObject } from "react";
import { useCallback, useEffect } from "react";

import type { RepoInfo } from "~/api";
import { ElementIds } from "~/api";
import { useKeybinding, useKeybindingDisplayText } from "~/common/keybindings/hooks.ts";
import { isDismissibleOverlayOpen } from "~/common/overlayUtils.ts";
import { useModifiedEnter } from "~/common/ShortcutUtils.ts";
import { KeyboardHint } from "~/components/KeyboardHint.tsx";

import { getMetaKey, isModifierPressed } from "../../../electron/utils.ts";
import styles from "./NewWorkspaceForm.module.scss";

type NewWorkspaceFormProps = {
  workspaceName: string;
  onWorkspaceNameChange: (value: string) => void;
  nameInputRef: RefObject<HTMLInputElement>;
  repoInfo: RepoInfo | null;
  isPending: boolean;
  // Extra gating from the parent (e.g. worktree mode requires a non-empty
  // branch name; submit must wait until the auto-fill preview returns).
  isSubmitDisabled?: boolean;
  onSubmit: () => void;
  autoFocus: boolean;
  children: ReactNode;
  branchField?: ReactNode;
};

export const NewWorkspaceForm = ({
  workspaceName,
  onWorkspaceNameChange,
  nameInputRef,
  repoInfo,
  isPending,
  isSubmitDisabled,
  onSubmit,
  autoFocus,
  children,
  branchField,
}: NewWorkspaceFormProps): ReactElement => {
  const sendMessageBinding = useKeybinding("send_message");
  const sendHint = useKeybindingDisplayText("send_message");

  const sendMessageTooltipContent = !repoInfo
    ? "Loading repository info..."
    : isPending
      ? "Agent is being created..."
      : isSubmitDisabled
        ? "Waiting for branch name..."
        : null;

  const isDisabled = (repoInfo && repoInfo.recentBranches?.length === 0) || isPending || !!isSubmitDisabled;

  const handleKeyPress = useModifiedEnter({
    onConfirm: onSubmit,
    sendMessageBinding,
  });

  const handleNameInputKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>): void => {
      if (e.key === "Enter" && isModifierPressed(e)) {
        e.preventDefault();
        onSubmit();
        return;
      }
      handleKeyPress(e.nativeEvent);
    },
    [onSubmit, handleKeyPress],
  );

  // Allow Cmd+Enter to submit from anywhere on the page, not just the input
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent): void => {
      if (e.key !== "Enter" || !isModifierPressed(e)) return;
      // An overlay open over the page (e.g. the Add Repository dialog) owns
      // Cmd+Enter for its own action; don't also create the workspace.
      if (isDismissibleOverlayOpen()) return;
      e.preventDefault();
      onSubmit();
    };

    document.addEventListener("keydown", handleGlobalKeyDown);
    return (): void => document.removeEventListener("keydown", handleGlobalKeyDown);
  }, [onSubmit]);

  return (
    <Flex direction="column" width="100%" gap="2">
      <div className={styles.formContainer} data-testid={ElementIds.TASK_STARTER}>
        <input
          ref={nameInputRef}
          type="text"
          value={workspaceName}
          onChange={(e): void => onWorkspaceNameChange(e.target.value)}
          onKeyDown={handleNameInputKeyDown}
          placeholder="Untitled workspace (optional)"
          className={styles.nameInput}
          data-testid={ElementIds.WORKSPACE_NAME_INPUT}
          autoFocus={autoFocus}
        />
        {branchField}
        <Flex align="center" justify="between" className={styles.toolbar}>
          <Flex align="center" gap="5" pl="1">
            {children}
          </Flex>
          <Flex align="center" gap="1" flexShrink="0">
            <Tooltip content={sendMessageTooltipContent ?? `${sendHint} to create workspace`}>
              <Button
                onClick={onSubmit}
                disabled={!!isDisabled}
                aria-label="Create Workspace"
                data-testid={ElementIds.START_TASK_BUTTON}
                size="2"
                className={styles.createButton}
              >
                Create workspace
              </Button>
            </Tooltip>
          </Flex>
        </Flex>
      </div>
      <Flex justify="end">
        <KeyboardHint keys={`${getMetaKey()}↵`} label="create" />
      </Flex>
    </Flex>
  );
};
