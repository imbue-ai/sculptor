import { Box, Button, Flex, Link, Text, Tooltip } from "@radix-ui/themes";
import { AlertTriangle, Terminal } from "lucide-react";
import type { FocusEvent, ReactElement } from "react";
import { useRef, useState } from "react";

import { ElementIds } from "~/api";
import { DEFAULT_WORKSPACE_SETUP_COMMAND } from "~/common/setupDefaults";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { useOnMountIf } from "~/common/useOnMountIf";

import styles from "./RepoRow.module.scss";

type RepoRowProps = {
  projectName: string;
  projectPath: string;
  agentCount: number;
  isPathAccessible: boolean;
  onRemove: () => void;
  shouldAutoFocusSetupCommand?: boolean;
  // null: tracking the current default. "": user cleared (no command runs).
  // Any other string: user's custom command.
  workspaceSetupCommand: string | null;
  onSetupCommandSave: (command: string | null) => void;
  namingPattern: string;
  onNamingPatternSave: (pattern: string) => void;
};

export const RepoRow = ({
  projectName,
  projectPath,
  agentCount,
  isPathAccessible,
  onRemove,
  shouldAutoFocusSetupCommand = false,
  workspaceSetupCommand,
  onSetupCommandSave,
  namingPattern,
  onNamingPatternSave,
}: RepoRowProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const isTrackingDefault = workspaceSetupCommand === null;
  const displayValue = workspaceSetupCommand ?? DEFAULT_WORKSPACE_SETUP_COMMAND;
  const [isExpanded, setIsExpanded] = useState<boolean>(() => shouldAutoFocusSetupCommand);
  const setupCommandTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  useOnMountIf(shouldAutoFocusSetupCommand, () => {
    setupCommandTextareaRef.current?.focus();
  });

  const handleSetupCommandBlur = (e: FocusEvent<HTMLTextAreaElement>): void => {
    const trimmed = e.target.value.trim();
    if (isTrackingDefault) {
      // Unchanged default text → remain tracking default. Otherwise freeze the edit.
      if (trimmed !== DEFAULT_WORKSPACE_SETUP_COMMAND) {
        onSetupCommandSave(trimmed);
      }
    } else if (trimmed !== workspaceSetupCommand) {
      onSetupCommandSave(trimmed);
    }
  };

  const handleReset = (): void => {
    onSetupCommandSave(null);
  };

  const handleNamingPatternBlur = (e: FocusEvent<HTMLInputElement>): void => {
    const trimmed = e.target.value.trim();
    if (trimmed !== namingPattern) {
      onNamingPatternSave(trimmed);
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
              key={workspaceSetupCommand}
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
