import { Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import styles from "./AccountFieldRow.module.scss";
import { SettingRow } from "./SettingRow.tsx";

type AccountFieldRowProps = {
  title: string;
  description: string;
  value: string;
  elementId?: string;
};

export const AccountFieldRow = ({ title, description, value, elementId }: AccountFieldRowProps): ReactElement => {
  const isUnset = value.trim().length === 0;
  return (
    <SettingRow title={title} description={description} data-testid={elementId}>
      {isUnset ? (
        <Text size="2" color="gray" className={styles.unsetValue}>
          Unset
        </Text>
      ) : (
        <Flex className={styles.readOnlyFieldNonEditable} align="center">
          <Text size="2">{value}</Text>
        </Flex>
      )}
    </SettingRow>
  );
};
