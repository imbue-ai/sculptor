import * as Dialog from "@radix-ui/react-dialog";
import { Cross1Icon } from "@radix-ui/react-icons";
import { Box, Button, Flex, IconButton, Text, VisuallyHidden } from "@radix-ui/themes";
import { FolderXIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds, type Project } from "../api";
import styles from "./RepoPathDialog.module.scss";

type RepoPathDialogProps = {
  isOpen: boolean;
  project: Project | null;
  onClose: () => void;
};

export const RepoPathDialog = ({ isOpen, project, onClose }: RepoPathDialogProps): ReactElement | null => {
  if (!project) {
    return null;
  }

  // Extract the path from the file:// URL
  const projectPath = project.userGitRepoUrl?.replace("file://", "") || "Unknown path";

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <VisuallyHidden>
        <Dialog.Title>Repo Path Not Found</Dialog.Title>
      </VisuallyHidden>
      <Dialog.Content
        className={styles.modalContainer}
        aria-describedby={undefined}
        data-testid={ElementIds.PROJECT_PATH_DIALOG}
      >
        <Flex direction="column" className={styles.body}>
          <Box className={styles.panel}>
            <Box position="absolute" top="4" right="4">
              <Dialog.Close asChild>
                <IconButton variant="ghost" size="1" aria-label="Close">
                  <Cross1Icon />
                </IconButton>
              </Dialog.Close>
            </Box>

            <Box className={styles.panelBody} py="4" px="4">
              <Flex direction="column" gap="4">
                <Flex align="center" gap="2">
                  <FolderXIcon size={24} className={styles.folderIcon} />
                  <Text size="5" weight="bold" className={styles.title}>
                    Repo Folder Not Found
                  </Text>
                </Flex>

                <Text className={styles.text}>
                  The repo folder for <Text weight="bold">{project.name}</Text> could not be found at:
                </Text>

                <Box className={styles.pathBox}>
                  <Text size="2" style={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                    {projectPath}
                  </Text>
                </Box>

                <Box className={styles.infoBox}>
                  <Text size="2" className={styles.text}>
                    <strong>Possible causes:</strong>
                  </Text>
                  <Box pl="3" pt="2">
                    <Flex direction="column" gap="1">
                      <Text size="2" className={styles.text}>
                        • The folder was moved to a different location
                      </Text>
                      <Text size="2" className={styles.text}>
                        • The folder was renamed
                      </Text>
                      <Text size="2" className={styles.text}>
                        • The folder was deleted
                      </Text>
                    </Flex>
                  </Box>
                </Box>

                <Box className={styles.helpBox}>
                  <Text size="2">
                    Please restore the repo folder to its original location. The system will automatically detect when
                    the path becomes available again.
                  </Text>
                </Box>
              </Flex>
            </Box>
          </Box>

          <Flex className={styles.footer} justify="end" p="3" gap="2">
            <Button
              onClick={onClose}
              className={styles.closeButton}
              data-testid={ElementIds.PROJECT_PATH_DIALOG_CLOSE_BUTTON}
            >
              Close
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};
