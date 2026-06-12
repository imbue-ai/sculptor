import { Flex, Text } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import styles from "./SettingsSection.module.scss";

type SettingsSectionProps = {
  description?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
};

export const SectionTitle = ({ children }: { children: ReactNode }): ReactElement => (
  <Text size="2" weight="medium" className={styles.sectionTitle} mb="2">
    {children}
  </Text>
);

export const SettingsSectionLayout = ({ description, toolbar, children }: SettingsSectionProps): ReactElement => (
  <Flex direction="column" className={styles.section}>
    {description && (
      <Text size="2" color="gray" mt="2" mb="7">
        {description}
      </Text>
    )}
    {toolbar}
    {children}
  </Flex>
);
