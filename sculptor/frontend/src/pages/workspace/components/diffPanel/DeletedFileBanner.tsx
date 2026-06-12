import { Button, Flex, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { AlertTriangle } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { fileBrowserTabCloseBehaviorAtom } from "~/common/state/atoms/userConfig.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import { closeDiffTabAtom } from "./atoms.ts";
import styles from "./DeletedFileBanner.module.scss";

type DeletedFileBannerProps = {
  workspaceId: string;
  filePath: string;
};

export const DeletedFileBanner = ({ workspaceId, filePath }: DeletedFileBannerProps): ReactElement => {
  const closeDiffTab = useSetAtom(closeDiffTabAtom);
  const tabCloseBehavior = useAtomValue(fileBrowserTabCloseBehaviorAtom);
  const dangerColor = useThemeDangerColor();

  const handleCloseTab = useCallback((): void => {
    closeDiffTab({ workspaceId, filePath, tabCloseBehavior });
  }, [closeDiffTab, workspaceId, filePath, tabCloseBehavior]);

  return (
    <Flex
      align="center"
      gap="2"
      px="3"
      py="2"
      flexShrink="0"
      className={styles.banner}
      data-testid="deleted-file-banner"
    >
      <AlertTriangle size={14} />
      <Text size="2">This file was deleted</Text>
      <span className={styles.spacer} />
      <Button variant="soft" size="1" color={dangerColor} onClick={handleCloseTab}>
        Close tab
      </Button>
    </Flex>
  );
};
