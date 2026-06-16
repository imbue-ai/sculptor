import { Select } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { LlmModel, type ModelOption } from "~/api";
import { getModelLongName } from "~/common/modelConstants";
import { sculptorSettingsAtom } from "~/common/state/atoms/sculptorSettings.ts";

const PRODUCTION_MODELS = [
  LlmModel.CLAUDE_FABLE_5,
  LlmModel.CLAUDE_4_OPUS_200K,
  LlmModel.CLAUDE_4_OPUS,
  LlmModel.CLAUDE_4_7_OPUS_200K,
  LlmModel.CLAUDE_4_7_OPUS,
  LlmModel.CLAUDE_4_6_OPUS_200K,
  LlmModel.CLAUDE_4_6_OPUS,
  LlmModel.CLAUDE_4_SONNET_200K,
  LlmModel.CLAUDE_4_SONNET,
  LlmModel.CLAUDE_4_HAIKU,
];

// Fake Claude is a testing-only model that returns deterministic responses without making LLM calls.
// Only shown when INTEGRATION_ENABLED is true.
const TESTING_ONLY_MODELS = [LlmModel.FAKE_CLAUDE, LlmModel.FAKE_CLAUDE_2];

type ModelSelectOptionsProps = {
  optionTestId?: string;
  // A harness-supplied model list (pi). When provided and non-empty these are
  // rendered (display_name label, model_id value); otherwise the built-in Claude
  // list is rendered unchanged. The Claude/creation/fallback path MUST keep its
  // PRODUCTION_MODELS display names — integration tests select by exact name.
  models?: ReadonlyArray<ModelOption>;
};

/**
 * Renders the model options for a Select dropdown.
 *
 * With a backend-supplied `models` list (pi) it renders those. Otherwise it
 * renders the built-in Claude models (Claude Code uses the user's existing
 * authentication); the Fake Claude models are appended only when integration
 * testing is enabled.
 */
export const ModelSelectOptions = ({ optionTestId, models }: ModelSelectOptionsProps): ReactElement => {
  const settings = useAtomValue(sculptorSettingsAtom);
  const isIntegrationTesting = settings?.TESTING?.INTEGRATION_ENABLED ?? false;

  if (models !== undefined && models.length > 0) {
    return (
      <>
        {models.map((model) => (
          <Select.Item key={model.modelId} value={model.modelId} data-testid={optionTestId}>
            {model.displayName}
          </Select.Item>
        ))}
      </>
    );
  }

  const claudeModels = isIntegrationTesting ? [...PRODUCTION_MODELS, ...TESTING_ONLY_MODELS] : PRODUCTION_MODELS;
  return (
    <>
      {claudeModels.map((modelValue) => (
        <Select.Item key={modelValue} value={modelValue} data-testid={optionTestId}>
          {getModelLongName(modelValue)}
        </Select.Item>
      ))}
    </>
  );
};
