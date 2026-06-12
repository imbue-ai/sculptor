import { Flex, Text } from "@radix-ui/themes";
import { AlertTriangle } from "lucide-react";
import type { ReactElement } from "react";

import styles from "./DiffErrorBanner.module.scss";

type DiffErrorBannerProps = {
  errorMessage: string;
};

export const DiffErrorBanner = ({ errorMessage }: DiffErrorBannerProps): ReactElement => {
  return (
    <Flex align="center" gap="2" px="3" py="2" flexShrink="0" className={styles.banner} data-testid="diff-error-banner">
      <AlertTriangle size={14} />
      <Text size="2">{errorMessage}</Text>
    </Flex>
  );
};
