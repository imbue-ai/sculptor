import { Flex, Select, Text, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { LlmModel } from "~/api";
import { ElementIds } from "~/api";
import { getModelShortName } from "~/common/modelConstants.ts";
import { ModelSelectOptions } from "~/components/ModelSelectOptions.tsx";
import { useCapabilityGate } from "~/components/useCapabilityGate.ts";

import styles from "./ModelSelector.module.scss";

type ModelSelectorProps = {
  model: LlmModel;
  onModelChange: (model: LlmModel) => void;
  /** The active task's `supports_model_selection` capability. When false the
   *  switcher renders disabled-with-tooltip (the current model still shows). */
  capabilityValue?: boolean;
};

export const ModelSelector = ({ model, onModelChange, capabilityValue }: ModelSelectorProps): ReactElement => {
  const gate = useCapabilityGate(capabilityValue, ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION);
  if (!gate.enabled) {
    // Radix Tooltip does not fire on a disabled trigger (pointer-events: none),
    // so the hover target and the test hook live on the wrapping span — the same
    // handling CapabilityGate uses.
    return (
      <Tooltip content={gate.tooltip}>
        <span data-testid={gate.elementId} style={{ display: "inline-flex" }}>
          <Select.Root size="1" value={model} disabled>
            <Select.Trigger className={styles.trigger} variant="ghost">
              <Flex align="center">
                <Text size="1">{getModelShortName(model)}</Text>
              </Flex>
            </Select.Trigger>
          </Select.Root>
        </span>
      </Tooltip>
    );
  }
  return (
    <Select.Root size="1" value={model} onValueChange={onModelChange}>
      <Select.Trigger className={styles.trigger} data-testid={ElementIds.MODEL_SELECTOR} variant="ghost">
        <Flex align="center">
          <Text size="1">{getModelShortName(model)}</Text>
        </Flex>
      </Select.Trigger>
      <Select.Content position="popper" sideOffset={5}>
        <Select.Group>
          <Select.Label>Model</Select.Label>
          <ModelSelectOptions optionTestId={ElementIds.MODEL_OPTION} />
        </Select.Group>
      </Select.Content>
    </Select.Root>
  );
};
