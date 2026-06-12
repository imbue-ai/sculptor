import { Flex, Text } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import styles from "./SettingRow.module.scss";

type SettingRowProps = {
  title: string;
  description: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  "data-testid"?: string;
};

export const SettingRow = ({ title, description, children, footer, ...props }: SettingRowProps): ReactElement => (
  <Flex direction="column" width="100%" py="4" className={styles.settingRow} data-testid={props["data-testid"]}>
    <Flex justify="between" align="center" gapX="7" gapY="3" className={styles.controlRow}>
      <Flex direction="column" className={styles.labelGroup}>
        <Text weight="medium">{title}</Text>
        <Text size="2" className={styles.descriptionText}>
          {description}
        </Text>
      </Flex>
      <div className={styles.control}>{children}</div>
    </Flex>
    {footer}
  </Flex>
);
