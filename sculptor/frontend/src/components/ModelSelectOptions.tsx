import { Select } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { LlmModel } from "~/api";
import { getModelLongName, PRODUCTION_MODELS } from "~/common/modelConstants";
import { sculptorSettingsAtom } from "~/common/state/atoms/sculptorSettings.ts";

// Fake Claude is a testing-only model that returns deterministic responses without making LLM calls.
// Only shown when INTEGRATION_ENABLED is true.
const TESTING_ONLY_MODELS = [LlmModel.FAKE_CLAUDE, LlmModel.FAKE_CLAUDE_2];

type ModelSelectOptionsProps = {
  optionTestId?: string;
};

/**
 * Renders the model options for a Select dropdown.
 * Only Claude models are available since Claude Code uses the user's existing authentication.
 * The Fake Claude model is only shown when integration testing is enabled.
 */
export const ModelSelectOptions = ({ optionTestId }: ModelSelectOptionsProps): ReactElement => {
  const settings = useAtomValue(sculptorSettingsAtom);
  const isIntegrationTesting = settings?.TESTING?.INTEGRATION_ENABLED ?? false;
  const models = isIntegrationTesting ? [...PRODUCTION_MODELS, ...TESTING_ONLY_MODELS] : PRODUCTION_MODELS;

  return (
    <>
      {models.map((modelValue) => (
        <Select.Item key={modelValue} value={modelValue} data-testid={optionTestId}>
          {getModelLongName(modelValue)}
        </Select.Item>
      ))}
    </>
  );
};
