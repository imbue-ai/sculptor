import { Box, Button, Flex, Spinner, Text, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";

import { ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { AddRepoForm } from "~/components/add-repo/AddRepoForm.tsx";
import { useAddRepo } from "~/components/add-repo/useAddRepo.tsx";
import { useDirectoryListing } from "~/components/path-autocomplete/useDirectoryListing.ts";

import styles from "./OnboardingWizard.module.scss";

const noopSetToast = (): void => {};

type AddRepoStepProps = {
  onComplete: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
};

export const AddRepoStep = ({ onComplete, isLoading, error }: AddRepoStepProps): ReactElement => {
  const [path, setPath] = useState("");
  const dangerColor = useThemeDangerColor();
  const { fetchDirectories } = useDirectoryListing();

  const { handleOpenNewRepo, handleBrowse, canBrowse, isValidating, validationDialogs } = useAddRepo({
    setToast: noopSetToast,
    onSuccess: onComplete,
  });

  const handleSubmit = useCallback(
    (value: string): void => {
      handleOpenNewRepo(value);
    },
    [handleOpenNewRepo],
  );

  return (
    <>
      <Flex direction="column" gap="2" data-testid={ElementIds.ONBOARDING_ADD_REPO_STEP}>
        <Text className={styles.titleText}>Add your first repo</Text>
        <Text color="gray" className={styles.secondaryText}>
          Point Sculptor at a repository to get started.
        </Text>

        <Box mt="3">
          <AddRepoForm
            fetchDirectories={fetchDirectories}
            path={path}
            onPathChange={setPath}
            onSubmit={handleSubmit}
            onBrowse={canBrowse ? handleBrowse : undefined}
            canBrowse={canBrowse}
            disabled={isValidating || isLoading}
            showDescription={false}
            autoFocus
          />
        </Box>

        {error && (
          <Text size="2" color={dangerColor} className={styles.error}>
            {error}
          </Text>
        )}

        <Tooltip content="Enter a repository path above" hidden={!!path.trim()}>
          <Button
            mt="1"
            size="3"
            variant="solid"
            className={styles.primaryButton}
            disabled={isValidating || isLoading || !path.trim()}
            onClick={() => handleSubmit(path.trim())}
            data-testid={ElementIds.ADD_REPO_SUBMIT_BUTTON}
          >
            {isValidating || isLoading ? <Spinner /> : "Add"}
          </Button>
        </Tooltip>
      </Flex>

      {validationDialogs}
    </>
  );
};
