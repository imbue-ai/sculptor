import { Button, DropdownMenu, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import type { LlmModel, ModelOption } from "~/api";
import { ElementIds } from "~/api";
import {
  getClaudeModelList,
  getModelLongName,
  getModelShortName,
  getProviderDisplayName,
  groupModelsByProvider,
  routeModelChange,
} from "~/common/modelConstants.ts";
import { isIntegrationTestingEnabledAtom } from "~/common/state/atoms/sculptorSettings.ts";
import { useCapabilityGate } from "~/components/useCapabilityGate.ts";

import styles from "./ModelSelector.module.scss";

type ModelSelectorProps = {
  model: LlmModel;
  /** The Claude per-turn change handler. Called when the harness sources no
   *  backend list (Claude); the selected model rides the next turn. */
  onModelChange: (model: LlmModel) => void;
  /** The active task's `supports_model_selection` capability. When false the
   *  switcher renders disabled-with-tooltip (the current model still shows). */
  capabilityValue?: boolean;
  /** A harness-supplied model list (pi). Options are keyed by model_id and
   *  `selectedModelId` is shown selected. */
  backendModels?: ReadonlyArray<ModelOption>;
  /** The model_id to show selected when the harness sources a backend list (pi). */
  selectedModelId?: string;
  /** The out-of-band change handler for a backend model list (pi). Called with
   *  the chosen `ModelOption` so the caller can apply it via the set-model
   *  endpoint; the value stays server-driven (selectedModelId) until it lands. */
  onBackendModelChange?: (option: ModelOption) => void;
  /** Whether the harness sources its catalog from a backend (pi); when false the
   *  built-in Claude list is shown. */
  sourcesBackendModels?: boolean;
  /** Invoked by the no-providers prompt to send the user to authenticate a provider. */
  onAuthenticate: () => void;
};

export const ModelSelector = ({
  model,
  onModelChange,
  capabilityValue,
  backendModels,
  selectedModelId,
  onBackendModelChange,
  sourcesBackendModels = false,
  onAuthenticate,
}: ModelSelectorProps): ReactElement => {
  const isIntegrationTesting = useAtomValue(isIntegrationTestingEnabledAtom);
  const gate = useCapabilityGate(capabilityValue, ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION);

  const models = backendModels ?? [];
  const hasBackendModels = sourcesBackendModels && models.length > 0;

  // The trigger label diverges by source: a backend list (pi) is labelled by the
  // selected model's display_name; the Claude path keeps its short name.
  const selectedBackendLabel =
    models.find((option) => option.modelId === selectedModelId)?.displayName ?? selectedModelId;
  const triggerLabel = sourcesBackendModels ? (selectedBackendLabel ?? "Select model") : getModelShortName(model);

  if (!gate.enabled) {
    // Radix Tooltip does not fire on a disabled trigger (pointer-events: none),
    // so the hover target and the test hook live on the wrapping span — the same
    // handling CapabilityGate uses.
    return (
      <Tooltip content={gate.tooltip}>
        <span data-testid={gate.elementId} style={{ display: "inline-flex" }}>
          <Button size="1" variant="ghost" className={styles.trigger} disabled>
            <Text size="1" truncate>
              {triggerLabel}
            </Text>
          </Button>
        </span>
      </Tooltip>
    );
  }

  if (sourcesBackendModels && models.length === 0) {
    // No authenticated providers: prompt the user to authenticate.
    return (
      <Tooltip content="Authenticate a provider to choose a model">
        <Button
          size="1"
          variant="ghost"
          className={styles.trigger}
          data-testid={ElementIds.MODEL_SELECTOR_AUTH_PROMPT}
          onClick={onAuthenticate}
        >
          <Text size="1" truncate>
            Authenticate a provider
          </Text>
        </Button>
      </Tooltip>
    );
  }

  if (sourcesBackendModels && models.length === 1) {
    // Nothing to switch to: a disabled trigger showing the current model, no
    // dropdown. No tooltip — this is not a capability denial.
    return (
      <Button size="1" variant="ghost" className={styles.trigger} data-testid={ElementIds.MODEL_SELECTOR} disabled>
        <Text size="1" truncate>
          {triggerLabel}
        </Text>
      </Button>
    );
  }

  // A backend list (pi) applies out-of-band via onBackendModelChange and stays
  // server-driven (value follows selectedModelId). The Claude path routes through
  // onModelChange and applies the model on the next turn.
  const onValueChange = (next: string): void => {
    routeModelChange(next, hasBackendModels ? models : undefined, onModelChange, onBackendModelChange);
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <Button size="1" variant="ghost" className={styles.trigger} data-testid={ElementIds.MODEL_SELECTOR}>
          <Text size="1" truncate>
            {triggerLabel}
          </Text>
          <DropdownMenu.TriggerIcon />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content>
        {hasBackendModels ? (
          <BackendModelItems models={models} selectedModelId={selectedModelId} onValueChange={onValueChange} />
        ) : (
          <ClaudeModelItems
            models={getClaudeModelList(isIntegrationTesting)}
            selectedModel={model}
            onValueChange={onValueChange}
          />
        )}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};

type BackendModelItemsProps = {
  models: ReadonlyArray<ModelOption>;
  selectedModelId?: string;
  onValueChange: (next: string) => void;
};

/**
 * The dropdown body for a backend catalog (pi). A single provider renders as a
 * non-selectable header over a flat radio list; two or more providers render as
 * a top-level entry per provider, each cascading into its own models.
 */
export const BackendModelItems = ({ models, selectedModelId, onValueChange }: BackendModelItemsProps): ReactElement => {
  const groups = groupModelsByProvider(models);

  if (groups.length === 1) {
    return (
      <>
        <DropdownMenu.Label>{getProviderDisplayName(groups[0].provider)}</DropdownMenu.Label>
        <ProviderRadioItems models={groups[0].models} selectedModelId={selectedModelId} onValueChange={onValueChange} />
      </>
    );
  }

  return (
    <>
      {groups.map((group) => (
        <DropdownMenu.Sub key={group.provider}>
          <DropdownMenu.SubTrigger data-testid={`${ElementIds.MODEL_PROVIDER_OPTION}-${group.provider}`}>
            {getProviderDisplayName(group.provider)}
          </DropdownMenu.SubTrigger>
          <DropdownMenu.SubContent>
            <ProviderRadioItems models={group.models} selectedModelId={selectedModelId} onValueChange={onValueChange} />
          </DropdownMenu.SubContent>
        </DropdownMenu.Sub>
      ))}
    </>
  );
};

type ProviderRadioItemsProps = {
  models: ReadonlyArray<ModelOption>;
  selectedModelId?: string;
  onValueChange: (next: string) => void;
};

const ProviderRadioItems = ({ models, selectedModelId, onValueChange }: ProviderRadioItemsProps): ReactElement => (
  <DropdownMenu.RadioGroup value={selectedModelId ?? ""} onValueChange={onValueChange}>
    {models.map((option) => (
      <DropdownMenu.RadioItem
        key={option.modelId}
        value={option.modelId}
        data-testid={`${ElementIds.MODEL_OPTION}-${option.modelId}`}
      >
        {option.displayName}
      </DropdownMenu.RadioItem>
    ))}
  </DropdownMenu.RadioGroup>
);

type ClaudeModelItemsProps = {
  models: ReadonlyArray<LlmModel>;
  selectedModel: LlmModel;
  onValueChange: (next: string) => void;
};

/**
 * The dropdown body for the built-in Claude list: a flat radio list keyed by
 * model id with the current model selected. Used when the harness sources no
 * backend catalog.
 */
export const ClaudeModelItems = ({ models, selectedModel, onValueChange }: ClaudeModelItemsProps): ReactElement => (
  <DropdownMenu.RadioGroup value={selectedModel} onValueChange={onValueChange}>
    {models.map((modelValue) => (
      <DropdownMenu.RadioItem
        key={modelValue}
        value={modelValue}
        data-testid={`${ElementIds.MODEL_OPTION}-${modelValue}`}
      >
        {getModelLongName(modelValue)}
      </DropdownMenu.RadioItem>
    ))}
  </DropdownMenu.RadioGroup>
);
