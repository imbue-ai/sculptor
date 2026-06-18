import { Flex, Select, Text, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { LlmModel, ModelOption } from "~/api";
import { ElementIds } from "~/api";
import { getModelShortName, routeModelChange } from "~/common/modelConstants.ts";
import { ModelSelectOptions } from "~/components/ModelSelectOptions.tsx";
import { useCapabilityGate } from "~/components/useCapabilityGate.ts";

import styles from "./ModelSelector.module.scss";

type ModelSelectorProps = {
  model: LlmModel;
  /** The Claude per-turn change handler. Called when no backend model list is
   *  present (Claude); the selected model rides the next turn. */
  onModelChange: (model: LlmModel) => void;
  /** The active task's `supports_model_selection` capability. When false the
   *  switcher renders disabled-with-tooltip (the current model still shows). */
  capabilityValue?: boolean;
  /** A harness-supplied model list (pi). When present and non-empty the switcher
   *  renders these options keyed by model_id and shows `selectedModelId` as its
   *  value; otherwise it renders the built-in Claude list keyed by `model`. */
  backendModels?: ReadonlyArray<ModelOption>;
  /** The model_id to show selected when `backendModels` is present (pi). */
  selectedModelId?: string;
  /** The out-of-band change handler for a backend model list (pi). Called with
   *  the chosen `ModelOption` so the caller can apply it via the set-model
   *  endpoint; the value stays server-driven (selectedModelId) until it lands. */
  onBackendModelChange?: (option: ModelOption) => void;
};

export const ModelSelector = ({
  model,
  onModelChange,
  capabilityValue,
  backendModels,
  selectedModelId,
  onBackendModelChange,
}: ModelSelectorProps): ReactElement => {
  const gate = useCapabilityGate(capabilityValue, ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION);
  const hasBackendModels = backendModels !== undefined && backendModels.length > 0;
  // A backend list with a single model has nothing to switch to, so the switcher
  // renders disabled (still showing the current model). The capability gate above
  // takes precedence over this.
  const isSingleBackendModel = hasBackendModels && backendModels.length <= 1;

  // The Select value and trigger label diverge by source: a backend list (pi) is
  // keyed and labelled by model_id / display_name; the Claude path keeps its
  // LlmModel value and short name unchanged.
  const value = hasBackendModels ? (selectedModelId ?? "") : model;
  const triggerLabel = hasBackendModels
    ? (backendModels.find((option) => option.modelId === selectedModelId)?.displayName ?? selectedModelId ?? "")
    : getModelShortName(model);

  if (!gate.enabled) {
    // Radix Tooltip does not fire on a disabled trigger (pointer-events: none),
    // so the hover target and the test hook live on the wrapping span — the same
    // handling CapabilityGate uses.
    return (
      <Tooltip content={gate.tooltip}>
        <span data-testid={gate.elementId} style={{ display: "inline-flex" }}>
          <Select.Root size="1" value={value} disabled>
            <Select.Trigger className={styles.trigger} variant="ghost">
              <Flex align="center">
                <Text size="1">{triggerLabel}</Text>
              </Flex>
            </Select.Trigger>
          </Select.Root>
        </span>
      </Tooltip>
    );
  }

  if (isSingleBackendModel) {
    // Nothing to switch to: render a disabled trigger showing the current model,
    // with no dropdown. No tooltip — this is not a capability denial.
    return (
      <Select.Root size="1" value={value} disabled>
        <Select.Trigger className={styles.trigger} data-testid={ElementIds.MODEL_SELECTOR} variant="ghost">
          <Flex align="center">
            <Text size="1">{triggerLabel}</Text>
          </Flex>
        </Select.Trigger>
      </Select.Root>
    );
  }

  // A backend list (pi) applies out-of-band via onBackendModelChange and stays
  // server-driven (value follows selectedModelId). The Claude path routes through
  // onModelChange and applies the model on the next turn.
  const onValueChange = (next: string): void => {
    routeModelChange(next, backendModels, onModelChange, onBackendModelChange);
  };

  return (
    <Select.Root size="1" value={value} onValueChange={onValueChange}>
      <Select.Trigger className={styles.trigger} data-testid={ElementIds.MODEL_SELECTOR} variant="ghost">
        <Flex align="center">
          <Text size="1">{triggerLabel}</Text>
        </Flex>
      </Select.Trigger>
      <Select.Content position="popper" sideOffset={5}>
        {hasBackendModels ? (
          // The backend (pi) list renders its own per-provider group headers, so
          // it is not wrapped in the single "Model" group the Claude list uses.
          <ModelSelectOptions optionTestId={ElementIds.MODEL_OPTION} models={backendModels} />
        ) : (
          <Select.Group>
            <Select.Label>Model</Select.Label>
            <ModelSelectOptions optionTestId={ElementIds.MODEL_OPTION} />
          </Select.Group>
        )}
      </Select.Content>
    </Select.Root>
  );
};
