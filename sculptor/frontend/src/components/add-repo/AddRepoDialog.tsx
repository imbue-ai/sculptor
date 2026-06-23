import { Button, Dialog, Flex, Spinner, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";

import { ElementIds } from "~/api";
import { useDirectoryListing } from "~/components/path-autocomplete/useDirectoryListing.ts";
import type { ToastContent } from "~/components/Toast.tsx";

import styles from "./AddRepoDialog.module.scss";
import { AddRepoForm } from "./AddRepoForm.tsx";
import { useAddRepo } from "./useAddRepo.tsx";

type AddRepoDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  setToast: (toast: ToastContent | null) => void;
};

export const AddRepoDialog = ({ open, onOpenChange, setToast }: AddRepoDialogProps): ReactElement => {
  const [path, setPath] = useState<string>("");

  const handleClose = useCallback(() => onOpenChange(false), [onOpenChange]);
  const { handleOpenNewRepo, handleBrowse, canBrowse, isValidating, validationDialogs } = useAddRepo({
    setToast,
    onSuccess: handleClose,
  });
  const { fetchDirectories } = useDirectoryListing();

  const handleAddClick = useCallback((): void => {
    if (path.trim()) {
      handleOpenNewRepo(path.trim());
    }
  }, [path, handleOpenNewRepo]);

  const handleOpenChange = useCallback(
    (isOpen: boolean): void => {
      // Prevent closing while validating
      if (!isOpen && isValidating) return;
      if (isOpen) {
        setPath("");
      }
      onOpenChange(isOpen);
    },
    [onOpenChange, isValidating],
  );

  return (
    <>
      <Dialog.Root open={open} onOpenChange={handleOpenChange}>
        <Dialog.Content maxWidth="480px" data-testid={ElementIds.ADD_REPO_DIALOG} className={styles.dialogContent}>
          <Dialog.Title>
            <Text size="5" weight="bold">
              Add new repository
            </Text>
          </Dialog.Title>

          <Flex direction="column" gap="4" mt="4">
            <AddRepoForm
              fetchDirectories={fetchDirectories}
              path={path}
              onPathChange={setPath}
              onSubmit={handleOpenNewRepo}
              onBrowse={canBrowse ? handleBrowse : undefined}
              canBrowse={canBrowse}
              disabled={isValidating}
            />
          </Flex>

          <Flex gap="3" mt="5" justify="end">
            <Button variant="soft" color="gray" disabled={isValidating} onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button
              variant="solid"
              data-testid={ElementIds.ADD_REPO_SUBMIT_BUTTON}
              disabled={isValidating || !path.trim()}
              onClick={handleAddClick}
            >
              {isValidating ? <Spinner size="2" /> : "Add new repository"}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>

      {validationDialogs}
    </>
  );
};
