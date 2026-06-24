import { Button, Dialog, Flex, TextArea } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useState } from "react";

import { UserConfigField } from "~/api";
import { commitPromptAtom } from "~/common/state/atoms/userConfig.ts";
import { useUserConfig } from "~/common/state/hooks/useUserConfig.ts";

type CommitPromptDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export const CommitPromptDialog = ({ open, onOpenChange }: CommitPromptDialogProps): ReactElement => {
  const commitPrompt = useAtomValue(commitPromptAtom);
  const { updateField } = useUserConfig();
  // Local draft of the prompt. While the dialog is open, reset the draft to the
  // committed value on each open transition and whenever that value changes, so
  // editing always starts from (and follows) the current commit prompt.
  const [promptValue, setPromptValue] = useState(commitPrompt);
  const [isPreviouslyOpen, setIsPreviouslyOpen] = useState(false);
  const [lastSyncedPrompt, setLastSyncedPrompt] = useState(commitPrompt);
  if (open && (!isPreviouslyOpen || commitPrompt !== lastSyncedPrompt)) {
    setIsPreviouslyOpen(true);
    setLastSyncedPrompt(commitPrompt);
    setPromptValue(commitPrompt);
  } else if (!open && isPreviouslyOpen) {
    setIsPreviouslyOpen(false);
  }

  const handleSave = async (): Promise<void> => {
    await updateField(UserConfigField.COMMIT_PROMPT, promptValue);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="500px">
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
