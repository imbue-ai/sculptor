import { Select } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import type { ModelOption } from "~/api";
import {
  getClaudeModelList,
  getModelLongName,
  getProviderDisplayName,
  groupModelsByProvider,
} from "~/common/modelConstants";
import { fakeModelDisplayNameAtom, isIntegrationTestingEnabledAtom } from "~/common/state/atoms/sculptorSettings.ts";

type ModelSelectOptionsProps = {
  // Base test id for the option items. Each item's `data-testid` is suffixed with
  // its own value (`<optionTestId>-<model id>`) so tests can target a specific
  // model by id rather than by display text.
  optionTestId?: string;
  // A harness-supplied model list (pi). When provided and non-empty these are
  // rendered grouped by provider (display_name label, model_id value); otherwise
  // the built-in Claude list is rendered unchanged. The Claude/creation/fallback
  // path MUST keep its model display names — integration tests select by exact name.
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
  const isIntegrationTesting = useAtomValue(isIntegrationTestingEnabledAtom);
  const fakeModelDisplayName = useAtomValue(fakeModelDisplayNameAtom);

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

  return (
    <>
      {getClaudeModelList(isIntegrationTesting, fakeModelDisplayName).map((modelValue) => (
        <Select.Item
          key={modelValue}
          value={modelValue}
          data-testid={optionTestId === undefined ? undefined : `${optionTestId}-${modelValue}`}
        >
          {getModelLongName(modelValue, fakeModelDisplayName)}
        </Select.Item>
      ))}
    </>
  );
};
