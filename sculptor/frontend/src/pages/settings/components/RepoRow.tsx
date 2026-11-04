import { Box, Button, Flex, Link, Text, Tooltip } from "@radix-ui/themes";
import { AlertTriangle, Terminal } from "lucide-react";
import type { FocusEvent, ReactElement } from "react";
import { useRef, useState } from "react";

import { ElementIds } from "~/api";
import { useOnMountIf } from "~/common/hooks/useOnMountIf";
import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { useNamingPatternMutation, useWorkspaceSetupCommandMutation } from "~/common/state/mutations/projects.ts";
import { getErrorMessage } from "~/common/utils/errors.ts";
import { DEFAULT_WORKSPACE_SETUP_COMMAND } from "~/common/utils/setupDefaults";

import styles from "./RepoRow.module.scss";

type RepoRowProps = {
  projectId: string;
  projectName: string;
  projectPath: string;
  agentCount: number;
  isPathAccessible: boolean;
  onRemove: () => void;
  shouldAutoFocusSetupCommand?: boolean;
  // null: tracking the current default. "": user cleared (no command runs).
  // Any other string: user's custom command.
  workspaceSetupCommand: string | null;
  namingPattern: string;
  setToast: (toast: ToastContent | null) => void;
};

type FieldElement = HTMLInputElement | HTMLTextAreaElement;

// Returns the `onError` for a save sent from `field`: it writes the saved text
// back over the rejected edit, unless the user has typed into the field since
// or it has re-mounted (and so already shows the saved text).
const revertOnError = (field: FieldElement | null, savedText: string): (() => void) => {
  const sentText = field?.value;
  return (): void => {
    if (field?.isConnected && field.value === sentText) {
      field.value = savedText;
    }
  };
};

export const RepoRow = ({
  projectId,
  projectName,
  projectPath,
  agentCount,
  isPathAccessible,
  onRemove,
  shouldAutoFocusSetupCommand = false,
  workspaceSetupCommand,
  namingPattern,
  setToast,
}: RepoRowProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const isTrackingDefault = workspaceSetupCommand === null;
  const displayValue = workspaceSetupCommand ?? DEFAULT_WORKSPACE_SETUP_COMMAND;
  const [isExpanded, setIsExpanded] = useState<boolean>(() => shouldAutoFocusSetupCommand);
  const setupCommandTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const { mutate: saveSetupCommand } = useWorkspaceSetupCommandMutation({
    onError: (error): void => {
      setToast({ type: ToastType.ERROR, title: getErrorMessage(error, "Failed to save setup command") });
    },
  });
  const { mutate: saveNamingPattern } = useNamingPatternMutation({
    onError: (error): void => {
      setToast({ type: ToastType.ERROR, title: getErrorMessage(error, "Failed to save naming pattern") });
    },
  });

  useOnMountIf(shouldAutoFocusSetupCommand, () => {
    setupCommandTextareaRef.current?.focus();
  });

  const handleSetupCommandSave = (command: string | null, field: HTMLTextAreaElement | null): void => {
    saveSetupCommand({ projectId, command }, { onError: revertOnError(field, displayValue) });
  };

  const handleSetupCommandBlur = (e: FocusEvent<HTMLTextAreaElement>): void => {
    const trimmed = e.target.value.trim();
    if (isTrackingDefault) {
      // Unchanged default text → remain tracking default. Otherwise freeze the edit.
      if (trimmed !== DEFAULT_WORKSPACE_SETUP_COMMAND) {
        handleSetupCommandSave(trimmed, e.target);
      }
    } else if (trimmed !== workspaceSetupCommand) {
      handleSetupCommandSave(trimmed, e.target);
    }
  };

  const handleReset = (): void => {
    handleSetupCommandSave(null, setupCommandTextareaRef.current);
  };

  const handleNamingPatternBlur = (e: FocusEvent<HTMLInputElement>): void => {
    const trimmed = e.target.value.trim();
    if (trimmed !== namingPattern) {
      saveNamingPattern({ projectId, pattern: trimmed }, { onError: revertOnError(e.target, namingPattern) });
    }
  };

  return (
    <Box className={styles.repoRow} data-testid={ElementIds.SETTINGS_REPO_ROW}>
      <Flex className={styles.repoRowHeader}>
        <Flex direction="column" className={styles.repoInfo}>
          <Flex align="center" className={styles.repoName}>
            <Text weight="medium">{projectName}</Text>
            {!isPathAccessible && (
              <Tooltip content="This repository path cannot be found">
                <AlertTriangle size={16} className={styles.warningIcon} />
              </Tooltip>
            )}
          </Flex>
          <Text className={styles.repoDetails}>
            <span className={styles.repoPath}>{projectPath}</span> —{" "}
            <span className={styles.agentCounts}>
              {agentCount} agent{agentCount !== 1 ? "s" : ""}
            </span>
          </Text>
        </Flex>
        <Flex align="center" gap="3" className={styles.repoActions}>
          <Link
            href="#"
            size="2"
            onClick={(e) => {
              e.preventDefault();
              setIsExpanded((prev) => !prev);
            }}
            aria-expanded={isExpanded}
            data-testid={ElementIds.SETTINGS_REPO_ROW_CONFIG_TOGGLE}
          >
            {isExpanded ? "Collapse" : "Configure"}
          </Link>
          <Button
            variant="solid"
            color={dangerColor}
            onClick={onRemove}
            data-testid={ElementIds.SETTINGS_REMOVE_REPO_BUTTON}
          >
            Remove repo & agents
          </Button>
        </Flex>
      </Flex>
      {isExpanded && (
        <Box className={styles.repoRowConfig}>
          <Box className={styles.setupCommandSection}>
            <Box className={styles.setupCommandLabelRow}>
              <label className={styles.setupCommandLabel}>
                <Terminal size={14} />
                Workspace setup command
              </label>
              {isTrackingDefault ? (
                <Text className={styles.setupCommandDefaultBadge}>Using default</Text>
              ) : (
                <Button variant="ghost" size="1" className={styles.setupCommandResetButton} onClick={handleReset}>
                  Reset to default
                </Button>
              )}
            </Box>
            {/* Uncontrolled: `key` re-mounts the textarea when the saved value changes
                (e.g. after blur-save or reset), so we never copy the prop into local state. */}
            <textarea
              ref={setupCommandTextareaRef}
              key={displayValue}
              className={`${styles.setupCommandInput} ${
                isTrackingDefault ? styles.setupCommandInputTrackingDefault : ""
              }`}
              defaultValue={displayValue}
              onBlur={handleSetupCommandBlur}
              placeholder="Leave blank to run nothing"
              rows={3}
              spellCheck={false}
              data-testid={ElementIds.SETTINGS_WORKSPACE_SETUP_COMMAND_INPUT}
            />
            <Text className={styles.setupCommandHint}>
              Runs in a terminal tab the first time a workspace is created from this repo. Uses your configured shell.
              Clear the field to disable; reset to follow future default changes.
            </Text>
          </Box>
          <Box className={styles.namingPatternSection}>
            <label className={styles.namingPatternLabel}>Branch-naming pattern</label>
            <input
              key={namingPattern}
              className={styles.namingPatternInput}
              defaultValue={namingPattern}
              onBlur={handleNamingPatternBlur}
              placeholder="(use global default)"
              spellCheck={false}
              data-testid={ElementIds.SETTINGS_NAMING_PATTERN_INPUT}
            />
            <Text className={styles.namingPatternHint}>Leave empty to use the global default.</Text>
          </Box>
        </Box>
      )}
    </Box>
  );
};
