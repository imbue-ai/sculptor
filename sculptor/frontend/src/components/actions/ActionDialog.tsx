import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { Button, Dialog, Flex, Select, Switch, Text, TextField } from "@radix-ui/themes";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import type { CustomAction, CustomActionGroup } from "~/api";
import { ElementIds } from "~/api";
import { Editor } from "~/components/Editor";

import styles from "./ActionDialog.module.scss";

// Sentinel Select values that don't map to a real group id.
const NO_GROUP_OPTION = "none";
const NEW_GROUP_OPTION = "new";

export type ActionFormData = {
  name: string;
  prompt: string;
  autoSubmit: boolean;
  groupId: string | null;
  newGroupName?: string;
};

type ActionDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action?: CustomAction;
  groups: ReadonlyArray<CustomActionGroup>;
  onSave: (formData: ActionFormData) => void;
};

export const ActionDialog = ({ open, onOpenChange, action, groups, onSave }: ActionDialogProps): ReactElement => {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [shouldAutoSubmit, setShouldAutoSubmit] = useState(true);
  const [groupId, setGroupId] = useState<string | null>(null);
  const [newGroupName, setNewGroupName] = useState("");

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      if (action) {
        setName(action.name);
        setPrompt(action.prompt);
        setShouldAutoSubmit(action.autoSubmit ?? true);
        setGroupId(action.groupId ?? null);
        setNewGroupName("");
      } else {
        setName("");
        setPrompt("");
        setShouldAutoSubmit(true);
        setGroupId(null);
        setNewGroupName("");
      }
    }
  }, [open, action]);

  const handleSave = useCallback((): void => {
    onSave({
      name,
      prompt,
      autoSubmit: shouldAutoSubmit,
      groupId: groupId === NEW_GROUP_OPTION ? null : groupId,
      newGroupName: groupId === NEW_GROUP_OPTION ? newGroupName : undefined,
    });
  }, [onSave, name, prompt, shouldAutoSubmit, groupId, newGroupName]);

  const isValid =
    name.trim() !== "" && prompt.trim() !== "" && (groupId !== NEW_GROUP_OPTION || newGroupName.trim() !== "");

  const handleKeyDown = useCallback(
    (e: KeyboardEvent): void => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && isValid) {
        e.preventDefault();
        handleSave();
      }
    },
    [isValid, handleSave],
  );

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className={styles.dialogContent} onKeyDown={handleKeyDown} data-testid={ElementIds.ACTION_DIALOG}>
        <Dialog.Title>{action ? "Edit Action" : "Add Action"}</Dialog.Title>
        <VisuallyHidden>
          <Dialog.Description>
            {action
              ? "Edit this action's name, prompt, group, and auto-submit behavior."
              : "Configure a new action's name, prompt, group, and auto-submit behavior."}
          </Dialog.Description>
        </VisuallyHidden>

        <Flex direction="column" gap="4">
          <Flex direction="column" gap="2">
            <Text size="2" weight="medium">
              Name
            </Text>
            <TextField.Root
              placeholder="Action name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid={ElementIds.ACTION_DIALOG_NAME_INPUT}
            />
          </Flex>

          <Flex direction="column" gap="2">
            <Text size="2" weight="medium">
              Prompt
            </Text>
            <Editor
              wrapperClassName={styles.promptEditor}
              placeholder="Action prompt"
              value={prompt}
              onChange={setPrompt}
              tagName={ElementIds.ACTION_DIALOG_PROMPT_INPUT}
              autoFocus={false}
            />
          </Flex>

          <Flex direction="column" gap="2">
            <Text size="2" weight="medium">
              Group
            </Text>
            <Select.Root
              value={groupId === null ? NO_GROUP_OPTION : groupId}
              onValueChange={(value) => setGroupId(value === NO_GROUP_OPTION ? null : value)}
            >
              <Select.Trigger placeholder="Select group" data-testid={ElementIds.ACTION_DIALOG_GROUP_SELECT} />
              <Select.Content>
                <Select.Item value={NO_GROUP_OPTION}>No group</Select.Item>
                {groups.map((group) => (
                  <Select.Item key={group.id} value={group.id}>
                    {group.name}
                  </Select.Item>
                ))}
                <Select.Item value={NEW_GROUP_OPTION}>+ Create new group...</Select.Item>
              </Select.Content>
            </Select.Root>
          </Flex>

          {groupId === NEW_GROUP_OPTION && (
            <Flex direction="column" gap="2">
              <Text size="2" weight="medium">
                New Group Name
              </Text>
              <TextField.Root
                placeholder="Group name"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                data-testid={ElementIds.ACTION_DIALOG_NEW_GROUP_NAME_INPUT}
              />
            </Flex>
          )}

          <Flex direction="row" gap="2" align="center">
            <Switch
              checked={shouldAutoSubmit}
              onCheckedChange={setShouldAutoSubmit}
              data-testid={ElementIds.ACTION_DIALOG_AUTO_SUBMIT_SWITCH}
            />
            <Text size="2">Auto-submit (send immediately)</Text>
          </Flex>

          <Flex gap="3" className={styles.actions} justify="end">
            <Dialog.Close>
              <Button variant="soft" color="gray">
                Cancel
              </Button>
            </Dialog.Close>
            <Button
              variant="solid"
              onClick={handleSave}
              disabled={!isValid}
              data-testid={ElementIds.ACTION_DIALOG_SAVE_BUTTON}
            >
              Save Action
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
};
