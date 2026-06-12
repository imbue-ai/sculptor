import { Button, Dialog, Flex, TextArea } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import type { UserConfigField } from "~/api";
import { commitPromptAtom } from "~/common/state/atoms/userConfig.ts";
import { useUserConfig } from "~/common/state/hooks/useUserConfig.ts";

type CommitPromptDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export const CommitPromptDialog = ({ open, onOpenChange }: CommitPromptDialogProps): ReactElement => {
  const commitPrompt = useAtomValue(commitPromptAtom);
  const { updateField } = useUserConfig();
  const [promptValue, setPromptValue] = useState(commitPrompt);

  useEffect(() => {
    if (open) {
      setPromptValue(commitPrompt);
    }
  }, [open, commitPrompt]);

  const handleSave = async (): Promise<void> => {
    await updateField("commitPrompt" as UserConfigField, promptValue);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content style={{ maxWidth: 500 }}>
        <Dialog.Title>Edit Commit Prompt</Dialog.Title>
        <Dialog.Description size="2" mb="4">
          This prompt is sent to the agent when you click Commit. The agent will commit your changes with an appropriate
          message.
        </Dialog.Description>
        <TextArea
          value={promptValue}
          onChange={(e) => setPromptValue(e.target.value)}
          rows={5}
          style={{ width: "100%" }}
        />
        <Flex gap="3" mt="4" justify="end">
          <Dialog.Close>
            <Button variant="soft" color="gray">
              Cancel
            </Button>
          </Dialog.Close>
          <Button variant="solid" onClick={handleSave}>
            Save
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};
