import { Select } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds, type LlmModel } from "~/api";
import { getModelLongName } from "~/common/utils/modelConstants.ts";
import { ModelSelectOptions } from "~/components/ModelSelectOptions.tsx";

import { SettingRow } from "./SettingRow.tsx";

const MOST_RECENTLY_USED = "None";

type DefaultModelSettingRowProps = {
  // The saved default, or null for "Most Recently Used".
  model: LlmModel | null;
  onChange: (model: LlmModel | null) => void;
  controlClassName?: string;
};

/**
 * Chooses the model new agents start with.
 *
 * The trigger names the saved model itself instead of echoing the matching option,
 * so a default the picker no longer lists still reads as what it is.
 */
export const DefaultModelSettingRow = ({
  model,
  onChange,
  controlClassName,
}: DefaultModelSettingRowProps): ReactElement => (
  <SettingRow title="Default Model" description="Select the default model for new agents.">
    <Select.Root
      value={model ?? MOST_RECENTLY_USED}
      onValueChange={(value) => onChange(value === MOST_RECENTLY_USED ? null : (value as LlmModel))}
    >
      <Select.Trigger
        variant="soft"
        className={controlClassName}
        data-testid={ElementIds.SETTINGS_DEFAULT_MODEL_SELECT}
      >
        {model === null ? "Most Recently Used" : getModelLongName(model)}
      </Select.Trigger>
      <Select.Content>
        <Select.Item key={MOST_RECENTLY_USED} value={MOST_RECENTLY_USED}>
          Most Recently Used
        </Select.Item>
        <ModelSelectOptions optionTestId={ElementIds.SETTINGS_DEFAULT_MODEL_OPTION} />
      </Select.Content>
    </Select.Root>
  </SettingRow>
);
