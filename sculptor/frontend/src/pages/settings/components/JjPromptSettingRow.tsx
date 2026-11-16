import { Button, Flex, Text, TextArea } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useState } from "react";

import { SettingRow } from "./SettingRow.tsx";
import styles from "./TextAreaSettingRow.module.scss";

type JjPromptSettingRowProps = {
  title: string;
  description: string;
  /** The jj prompt, or null while the git prompt is used in its place. */
  value: string | null;
  /** The git prompt a jj workspace is sent while `value` is null. */
  gitPrompt: string;
  /** The jj wording one click sets. */
  suggestedPrompt: string;
  /** Called with the new jj prompt, or null to go back to the git prompt. */
  onSave: (value: string | null) => void;
  "data-testid"?: string;
};

/**
 * An optional jj prompt that a jj workspace is sent instead of a git prompt.
 * While unset it shows the git prompt it falls back to and offers a suggested
 * jj wording; once set it is an editable field, and clearing it goes back to
 * the git prompt.
 */
export const JjPromptSettingRow = ({
  title,
  description,
  value,
  gitPrompt,
  suggestedPrompt,
  onSave,
  "data-testid": dataTestId,
}: JjPromptSettingRowProps): ReactElement => {
  // Local draft of the field, resynced during render whenever the saved value changes.
  const [draft, setDraft] = useState<string>(value ?? "");
  const [syncedValue, setSyncedValue] = useState<string | null>(value);
  if (syncedValue !== value) {
    setSyncedValue(value);
    setDraft(value ?? "");
  }

  const handleBlur = (): void => {
    const next = draft.trim() === "" ? null : draft;
    if (next !== value) {
      onSave(next);
    }
  };

  return (
    <SettingRow
      title={title}
      description={description}
      data-testid={dataTestId}
      footer={
        <Flex mt="4" width="100%" direction="column" gap="1">
          {value === null ? (
            <>
              <Text size="1" color="gray">
                Uses the git prompt:
              </Text>
              <Text size="2" color="gray">
                {gitPrompt}
              </Text>
            </>
          ) : (
            <TextArea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={handleBlur}
              rows={4}
              className={styles.textArea}
            />
          )}
        </Flex>
      }
    >
      {value === null ? (
        <Button variant="soft" size="1" onClick={() => onSave(suggestedPrompt)}>
          Use suggested wording
        </Button>
      ) : (
        <Button variant="ghost" size="1" mr="2" onClick={() => onSave(null)}>
          Use the git prompt
        </Button>
      )}
    </SettingRow>
  );
};
