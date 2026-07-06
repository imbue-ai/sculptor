import { Button, Flex, Text } from "@radix-ui/themes";
import { AlertTriangle } from "lucide-react";
import type { ReactElement } from "react";

import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import styles from "./DeletedFileBanner.module.scss";

type DeletedFileBannerProps = {
  /** Dismiss the deleted file. The embedding viewer clears both the shared diff
   *  tab and the host panel's local click selection, so the close takes effect
   *  regardless of which source drove the view. */
  onClose: () => void;
};

export const DeletedFileBanner = ({ onClose }: DeletedFileBannerProps): ReactElement => {
  const dangerColor = useThemeDangerColor();

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
      <Button variant="soft" size="1" color={dangerColor} onClick={onClose}>
        Close tab
      </Button>
    </Flex>
  );
};
