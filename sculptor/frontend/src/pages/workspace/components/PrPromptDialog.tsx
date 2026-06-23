import { Button, Dialog, Flex, TextArea } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { ElementIds, UserConfigField } from "../../../api";
import { prCreationPromptAtom } from "../../../common/state/atoms/userConfig.ts";
import { useUserConfig } from "../../../common/state/hooks/useUserConfig.ts";
import type { GitProvider } from "./PrButton.tsx";

type PrPromptDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  gitProvider: GitProvider;
};

export const PrPromptDialog = ({ open, onOpenChange, gitProvider }: PrPromptDialogProps): ReactElement => {
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const { updateField } = useUserConfig();
  const [promptValue, setPromptValue] = useState(prCreationPrompt);

  useEffect(() => {
    if (open) {
      setPromptValue(prCreationPrompt);
    }
  }, [open, prCreationPrompt]);

  const handleSave = async (): Promise<void> => {
    await updateField(UserConfigField.PR_CREATION_PROMPT, promptValue);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content maxWidth="500px" data-testid={ElementIds.PR_PROMPT_DIALOG}>
        <Dialog.Title>Edit PR Creation Prompt</Dialog.Title>
        <Dialog.Description size="2" mb="4">
          This prompt is sent to the agent when you click {gitProvider === "gitlab" ? "Create MR" : "Create PR"}. The
          agent will push your changes and create the {gitProvider === "gitlab" ? "merge request" : "pull request"}.
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
