import { Button, Flex, Text, TextField } from "@radix-ui/themes";
import type { FormEvent, ReactElement } from "react";
import { useState } from "react";

import { getErrorMessage } from "~/common/utils/errors.ts";

import type { JjIdentity } from "../../../api";
import { ElementIds } from "../../../api";

type JjIdentityFormProps = {
  suggestion: JjIdentity;
  onSave: (identity: JjIdentity) => Promise<void>;
};

/** One-click form that writes jj's `user.name` and `user.email` into the user's jj config. */
export const JjIdentityForm = ({ suggestion, onSave }: JjIdentityFormProps): ReactElement => {
  const [name, setName] = useState(suggestion.name);
  const [email, setEmail] = useState(suggestion.email);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const identity = { name: name.trim(), email: email.trim() };
  const canSave = identity.name !== "" && identity.email !== "" && !isSaving;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setIsSaving(true);
    setSaveError(null);
    try {
      await onSave(identity);
    } catch (error) {
      setSaveError(getErrorMessage(error, "Could not save the identity"));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={(event) => void handleSubmit(event)} data-testid={ElementIds.JJ_IDENTITY_FORM}>
      <Flex direction="column" gap="2" minWidth="300px">
        <TextField.Root
          placeholder="Name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          data-testid={ElementIds.JJ_IDENTITY_NAME_INPUT}
        />
        <TextField.Root
          type="email"
          placeholder="Email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          data-testid={ElementIds.JJ_IDENTITY_EMAIL_INPUT}
        />
        <Flex>
          <Button type="submit" variant="soft" disabled={!canSave} data-testid={ElementIds.JJ_IDENTITY_SUBMIT}>
            Save identity
          </Button>
        </Flex>
        {saveError && (
          <Text size="2" color="red">
            {saveError}
          </Text>
        )}
      </Flex>
    </form>
  );
};
