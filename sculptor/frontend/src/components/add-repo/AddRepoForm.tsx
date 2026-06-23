import { Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback } from "react";

import type { DirectoryEntry } from "~/api";
import { ElementIds } from "~/api";
import { PathAutocomplete } from "~/components/path-autocomplete/PathAutocomplete.tsx";

import styles from "./AddRepoForm.module.scss";

type AddRepoFormProps = {
  fetchDirectories: (path: string) => Promise<Array<DirectoryEntry>>;
  path: string;
  onPathChange: (path: string) => void;
  onSubmit: (path: string) => void;
  onBrowse?: () => Promise<string | undefined>;
  canBrowse?: boolean;
  disabled?: boolean;
  showDescription?: boolean;
  autoFocus?: boolean;
};

export const AddRepoForm = ({
  fetchDirectories,
  path,
  onPathChange,
  onSubmit,
  onBrowse,
  canBrowse = false,
  disabled = false,
  showDescription = true,
  autoFocus = false,
}: AddRepoFormProps): ReactElement => {
  const handleBrowseClick = useCallback(async (): Promise<void> => {
    if (disabled || !onBrowse) return;
    const selectedPath = await onBrowse();
    if (selectedPath) {
      onPathChange(selectedPath);
    }
  }, [disabled, onBrowse, onPathChange]);

  return (
    <Flex direction="column" gap="3">
      {showDescription && (
        <Text size="2" className={styles.description}>
          Start typing to search for a repository.
        </Text>
      )}
      <PathAutocomplete
        placeholder="~/path/to/repo"
        value={path}
        onValueChange={onPathChange}
        onSubmit={onSubmit}
        fetchDirectories={fetchDirectories}
        disabled={disabled}
        inputTestId={ElementIds.ADD_REPO_PATH_INPUT}
        autoFocus={autoFocus}
      />
      {canBrowse && onBrowse && (
        <Text size="2" className={styles.browseHint}>
          Or{" "}
          <span
            className={styles.browseLink}
            onClick={handleBrowseClick}
            aria-disabled={disabled}
            data-testid={ElementIds.ADD_REPO_BROWSE_LINK}
          >
            browse
          </span>{" "}
          for a folder
        </Text>
      )}
    </Flex>
  );
};
