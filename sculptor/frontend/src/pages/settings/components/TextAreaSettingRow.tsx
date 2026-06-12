import { Button, Flex, TextArea, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { SettingRow } from "./SettingRow.tsx";
import styles from "./TextAreaSettingRow.module.scss";

type TextAreaSettingRowProps = {
  title: string;
  description: string;
  value: string;
  defaultValue: string;
  onSave: (value: string) => void;
  textAreaTestId?: string;
  disabled?: boolean;
};

export const TextAreaSettingRow = ({
  title,
  description,
  value,
  defaultValue,
  onSave,
  textAreaTestId,
  disabled = false,
}: TextAreaSettingRowProps): ReactElement => {
  const [localValue, setLocalValue] = useState(value);

  useEffect(() => setLocalValue(value), [value]);

  const handleBlur = (): void => {
    if (localValue !== value) {
      onSave(localValue);
    }
  };

  const handleReset = (): void => {
    setLocalValue(defaultValue);
    onSave(defaultValue);
  };

  return (
    <SettingRow
      title={title}
      description={description}
      footer={
        <Flex mt="4" width="100%">
          <TextArea
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            onBlur={handleBlur}
            rows={4}
            className={styles.textArea}
            data-testid={textAreaTestId}
            disabled={disabled}
          />
        </Flex>
      }
    >
      <Tooltip content="Already using the default value" hidden={localValue !== defaultValue}>
        <Button
          variant="ghost"
          size="1"
          mr="2"
          disabled={disabled || localValue === defaultValue}
          onClick={handleReset}
        >
          Reset to default
        </Button>
      </Tooltip>
    </SettingRow>
  );
};
