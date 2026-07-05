import { Button, Dialog, Flex, TextArea } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useState } from "react";

import { ElementIds, UserConfigField } from "../../api";
import { prCreationPromptAtom } from "../../common/state/atoms/userConfig.ts";
import { useUserConfig } from "../../common/state/hooks/useUserConfig.ts";

type PrPromptDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export const PrPromptDialog = ({ open, onOpenChange }: PrPromptDialogProps): ReactElement => {
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const { updateField } = useUserConfig();
  const [promptValue, setPromptValue] = useState(prCreationPrompt);

  // While the dialog is open, keep the editor seeded with the saved prompt:
  // re-sync on open and whenever the saved value changes underneath us.
  // Adjusting state during render (with previous-value guards) avoids the
  // stale frame an effect would produce.
  const [isOpenOnPrevRender, setIsOpenOnPrevRender] = useState(open);
  const [prevPrompt, setPrevPrompt] = useState(prCreationPrompt);
  if (open && (open !== isOpenOnPrevRender || prCreationPrompt !== prevPrompt)) {
    setPromptValue(prCreationPrompt);
  }

  if (open !== isOpenOnPrevRender) {
    setIsOpenOnPrevRender(open);
  }

  if (prCreationPrompt !== prevPrompt) {
    setPrevPrompt(prCreationPrompt);
  }

  const handleSave = async (): Promise<void> => {
    await updateField(UserConfigField.PR_CREATION_PROMPT, promptValue);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="500px" data-testid={ElementIds.PR_PROMPT_DIALOG}>
        <Dialog.Title>Edit PR Creation Prompt</Dialog.Title>
        <Dialog.Description size="2" mb="4">
          This prompt is sent to the agent when you click Create PR. The agent will push your changes and create the
          pull request.
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
