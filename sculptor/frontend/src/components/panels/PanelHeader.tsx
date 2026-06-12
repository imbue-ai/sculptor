import { Flex, Text } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import styles from "./PanelHeader.module.scss";

type PanelHeaderProps = {
  title: string;
  /** Optional content rendered to the right of the title (e.g. icon buttons). */
  actions?: ReactNode;
  /** Optional content rendered next to the title text (e.g. status indicators). */
  afterTitle?: ReactNode;
};

export const PanelHeader = ({ title, actions, afterTitle }: PanelHeaderProps): ReactElement => (
  <div className={styles.header}>
    <Flex align="center" gap="2">
      <Text size="2" weight="medium">
        {title}
      </Text>
      {afterTitle}
    </Flex>
    {actions && (
      <Flex align="center" gap="2">
        {actions}
      </Flex>
    )}
  </div>
);
