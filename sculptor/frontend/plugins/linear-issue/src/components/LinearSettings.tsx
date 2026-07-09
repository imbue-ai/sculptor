import { Flex, Text, TextArea, TextField } from "@radix-ui/themes";
import { usePluginSetting } from "@sculptor/plugin-sdk";
import { useQueryClient } from "@tanstack/react-query";
import type { ReactElement, ReactNode } from "react";

import { PLUGIN_ID } from "../constants.ts";
import { DEFAULT_PROMPT_TEMPLATE, DEFAULT_TITLE_TEMPLATE } from "../linear/templates.ts";

/**
 * Plugin settings: the Linear personal API key, plus the templates that seed
 * the new-workspace dialog when a workspace is created from a board ticket.
 */
export const LinearSettings = (): ReactElement => {
  const [apiKey, setApiKey] = usePluginSetting("apiKey");
  const [titleTemplate, setTitleTemplate] = usePluginSetting("template:title");
  const [branchTemplate, setBranchTemplate] = usePluginSetting("template:branch");
  const [promptTemplate, setPromptTemplate] = usePluginSetting("template:prompt");
  const queryClient = useQueryClient();

  const handleKeyChange = (value: string): void => {
    setApiKey(value);
    // Cached issues were fetched with the old key (deliberately not part of any
    // query key) — drop this plugin's namespace so panels refetch with the new
    // credentials. Template edits need no such invalidation: they are read at
    // create-workspace click time, not baked into cached queries.
    void queryClient.invalidateQueries({ queryKey: [PLUGIN_ID] });
  };

  return (
    <Flex direction="column" gap="4" style={{ maxWidth: 460 }}>
      <Flex direction="column" gap="2">
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
      <Flex direction="column" gap="2">
        <Text size="2" weight="medium">
          New workspace templates
        </Text>
        <Text size="1" color="gray">
          Seeds for workspaces created from board tickets. Variables: {"{identifier}"}, {"{identifierLower}"},{" "}
          {"{title}"}, {"{titleSlug}"}, {"{url}"}, {"{description}"}. Leave a field blank to use its default.
        </Text>
        <TemplateField label="Title">
          <TextField.Root
            placeholder={DEFAULT_TITLE_TEMPLATE}
            value={titleTemplate}
            onChange={(e) => setTitleTemplate(e.target.value)}
          />
        </TemplateField>
        <TemplateField label="Branch">
          <TextField.Root
            placeholder="Derived from the title"
            value={branchTemplate}
            onChange={(e) => setBranchTemplate(e.target.value)}
          />
        </TemplateField>
        <TemplateField label="Prompt">
          <TextArea
            rows={4}
            placeholder={DEFAULT_PROMPT_TEMPLATE}
            value={promptTemplate}
            onChange={(e) => setPromptTemplate(e.target.value)}
          />
        </TemplateField>
      </Flex>
    </Flex>
  );
};

/** A labeled template input; the wrapping <label> gives the field its accessible name. */
const TemplateField = ({ label, children }: { label: string; children: ReactNode }): ReactElement => (
  <label>
    <Text size="1" weight="medium" as="div" mb="1">
      {label}
    </Text>
    {children}
  </label>
);
