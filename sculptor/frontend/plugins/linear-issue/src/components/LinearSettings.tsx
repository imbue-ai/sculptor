import { Flex, Text, TextField } from "@radix-ui/themes";
import { usePluginSetting } from "@sculptor/plugin-sdk";
import { useQueryClient } from "@tanstack/react-query";
import type { ReactElement } from "react";

import { PLUGIN_ID } from "../constants.ts";

/** Plugin settings: the Linear personal API key, stored via the SDK. */
export const LinearSettings = (): ReactElement => {
  const [apiKey, setApiKey] = usePluginSetting("apiKey");
  const queryClient = useQueryClient();

  const handleKeyChange = (value: string): void => {
    setApiKey(value);
    // Cached issues were fetched with the old key (deliberately not part of any
    // query key) — drop this plugin's namespace so panels refetch with the new
    // credentials.
    void queryClient.invalidateQueries({ queryKey: [PLUGIN_ID] });
  };

  return (
    <Flex direction="column" gap="2" style={{ maxWidth: 460 }}>
      <Text size="1" color="gray">
        Personal API key from Linear → Settings → Security &amp; access → Personal API keys. Stored locally in this
        browser only.
      </Text>
      <TextField.Root
        type="password"
        placeholder="lin_api_..."
        value={apiKey}
        onChange={(e) => handleKeyChange(e.target.value)}
      />
    </Flex>
  );
};
