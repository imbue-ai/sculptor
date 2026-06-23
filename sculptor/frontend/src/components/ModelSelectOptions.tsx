import { Select } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { LlmModel, type ModelOption } from "~/api";
import { getModelLongName, getProviderDisplayName } from "~/common/modelConstants";
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
] as const satisfies ReadonlyArray<LlmModel>;

// Fake Claude is a testing-only model that returns deterministic responses without making LLM calls.
// Only shown when INTEGRATION_ENABLED is true.
const TESTING_ONLY_MODELS = [LlmModel.FAKE_CLAUDE, LlmModel.FAKE_CLAUDE_2] as const satisfies ReadonlyArray<LlmModel>;

type ProviderGroup = {
  provider: string;
  models: ReadonlyArray<ModelOption>;
};

// Partition the catalog into per-provider groups, preserving incoming order:
// the backend delivers it newest-first, which we keep within and across groups.
const groupModelsByProvider = (models: ReadonlyArray<ModelOption>): ReadonlyArray<ProviderGroup> => {
  const order: Array<string> = [];
  const byProvider = new Map<string, Array<ModelOption>>();
  for (const model of models) {
    const existing = byProvider.get(model.provider);
    if (existing === undefined) {
      order.push(model.provider);
      byProvider.set(model.provider, [model]);
    } else {
      existing.push(model);
    }
  }
  return order.map((provider) => ({ provider, models: byProvider.get(provider) ?? [] }));
};

type ModelSelectOptionsProps = {
  // Base test id for the option items. Each item's `data-testid` is suffixed with
  // its own value (`<optionTestId>-<model id>`) so tests can target a specific
  // model by id rather than by display text.
  optionTestId?: string;
  // A harness-supplied model list (pi). When provided and non-empty these are
  // rendered grouped by provider (display_name label, model_id value); otherwise
  // the built-in Claude list is rendered unchanged. The Claude/creation/fallback
  // path MUST keep its PRODUCTION_MODELS display names — integration tests select
  // by exact name.
  models?: ReadonlyArray<ModelOption>;
};

/**
 * Renders the model options for a Select dropdown.
 *
 * With a backend-supplied `models` list (pi) it renders those grouped by
 * provider, each group led by a non-selectable provider header. Otherwise it
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
        {groupModelsByProvider(models).map((group) => (
          <Select.Group key={group.provider}>
            <Select.Label>{getProviderDisplayName(group.provider)}</Select.Label>
            {group.models.map((model) => (
              <Select.Item
                key={model.modelId}
                value={model.modelId}
                data-testid={optionTestId === undefined ? undefined : `${optionTestId}-${model.modelId}`}
              >
                {model.displayName}
              </Select.Item>
            ))}
          </Select.Group>
        ))}
      </>
    );
  }

  const claudeModels = isIntegrationTesting ? [...PRODUCTION_MODELS, ...TESTING_ONLY_MODELS] : PRODUCTION_MODELS;
  return (
    <>
      {claudeModels.map((modelValue) => (
        <Select.Item
          key={modelValue}
          value={modelValue}
          data-testid={optionTestId === undefined ? undefined : `${optionTestId}-${modelValue}`}
        >
          {getModelLongName(modelValue)}
        </Select.Item>
      ))}
    </>
  );
};
