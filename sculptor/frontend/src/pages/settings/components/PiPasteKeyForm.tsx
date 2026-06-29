import { Button, Flex, Text, TextField } from "@radix-ui/themes";
import { type ReactElement, useCallback, useState } from "react";

import { ElementIds, writePiProviderKey } from "~/api";
import { HTTPException } from "~/common/Errors.ts";

type PiPasteKeyFormProps = {
  providerId: string;
  onSaved: () => void;
};

/**
 * The power-user paste-key path for a single-key provider, shown in the login modal.
 * The value is written verbatim to auth.json by the backend; the hint nudges toward
 * $ENV / !command so the literal key need not be stored.
 */
export const PiPasteKeyForm = ({ providerId, onSaved }: PiPasteKeyFormProps): ReactElement => {
  const [keyValue, setKeyValue] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSave = useCallback(async (): Promise<void> => {
    setErrorMessage(null);
    try {
      await writePiProviderKey({ body: { providerId, keyValue }, meta: { skipWsAck: true } });
      setKeyValue("");
      onSaved();
    } catch (error) {
      const detail = error instanceof HTTPException ? error.detail : undefined;
      setErrorMessage(detail ?? "Could not save the API key.");
    }
  }, [providerId, keyValue, onSaved]);

  return (
    <Flex direction="column" gap="2">
      <Flex gap="2" align="center">
        <TextField.Root
          placeholder="sk-… or $MY_KEY or !op read …"
          value={keyValue}
          onChange={(event) => setKeyValue(event.target.value)}
          data-testid={ElementIds.PI_PASTE_KEY_INPUT}
          style={{ flexGrow: 1 }}
        />
        <Button
          variant="solid"
          onClick={() => void handleSave()}
          disabled={!keyValue.trim()}
          data-testid={ElementIds.PI_PASTE_KEY_SAVE}
        >
          Save credential
        </Button>
      </Flex>
      <Text size="1" color="gray">
        Stored verbatim in ~/.pi/agent/auth.json. Use $ENV_VAR or !command to avoid storing the literal key.
      </Text>
      {errorMessage !== null && (
        <Text size="2" color="red">
          {errorMessage}
        </Text>
      )}
    </Flex>
  );
};
