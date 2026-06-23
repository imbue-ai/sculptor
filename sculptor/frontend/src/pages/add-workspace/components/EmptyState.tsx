import { Flex, Text } from "@radix-ui/themes";
import { FolderIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./EmptyState.module.scss";

export const EmptyState = (): ReactElement => {
  return (
    <Flex direction="column" align="center" className={styles.container}>
      <FolderIcon size={48} strokeWidth={1.5} className={styles.icon} />
      <Text className={styles.heading} data-testid={ElementIds.ADD_WORKSPACE_EMPTY_STATE}>
        No workspaces yet
      </Text>
      <Text className={styles.description}>Describe what you need above to create your first workspace.</Text>
    </Flex>
  );
};
