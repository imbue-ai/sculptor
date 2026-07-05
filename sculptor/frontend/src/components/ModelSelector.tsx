import { Button, DropdownMenu, Flex, Select, Text, Tooltip } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { LlmModel, ModelOption } from "~/api";
import { ElementIds } from "~/api";
import { useCapabilityGate } from "~/common/hooks/useCapabilityGate.ts";
import {
  getModelShortName,
  getProviderDisplayName,
  groupModelsByProvider,
  routeModelChange,
} from "~/common/modelConstants.ts";
import { ModelSelectOptions } from "~/components/ModelSelectOptions.tsx";

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
   *  built-in Claude list is shown. An empty `backendModels` then means "no
   *  authenticated providers" — show the login CTA, not the Claude fallback list. */
  sourcesBackendModels?: boolean;
  /** Invoked by the no-providers prompt to send the user to authenticate a
   *  provider (the pi login flow under Settings -> Pi). */
  onAuthenticate: () => void;
};

const PI_NO_MODELS_COPY = "No models available — please log in to authenticate";

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
  const gate = useCapabilityGate(capabilityValue, ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION);

  const models = backendModels ?? [];
  const hasBackendModels = sourcesBackendModels && models.length > 0;
  const providerGroups = hasBackendModels ? groupModelsByProvider(models) : [];

  // The Select value / trigger label diverge by source: a backend list (pi) is
  // keyed and labelled by model_id / display_name; the Claude path keeps its
  // LlmModel value and short name.
  const value = hasBackendModels ? (selectedModelId ?? "") : model;
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

  if (sourcesBackendModels && models.length === 0) {
    // pi with no authenticated providers: an empty catalog is genuinely "nothing to
    // authenticate as", not a cue to fall back to the Claude list. Show the locked
    // copy + a CTA into the login flow.
    return (
      <Flex align="center" gap="2" data-testid={ElementIds.PI_PICKER_EMPTY_STATE}>
        <Text size="1" color="gray">
          {PI_NO_MODELS_COPY}
        </Text>
        <Button size="1" variant="ghost" onClick={onAuthenticate} data-testid={ElementIds.PI_PICKER_LOGIN_CTA}>
          Open pi login
        </Button>
      </Flex>
    );
  }

  if (sourcesBackendModels && models.length === 1) {
    // Nothing to switch to: a disabled trigger showing the current model, no
    // dropdown. No tooltip — this is not a capability denial.
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
    routeModelChange(next, hasBackendModels ? models : undefined, onModelChange, onBackendModelChange);
  };

  if (providerGroups.length >= 2) {
    // Multiple providers cascade into a per-provider submenu. Radix Select cannot
    // nest submenus, so this case uses a DropdownMenu; the flat single-provider
    // and Claude cases below stay on the Select primitive.
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
          <CascadingProviderMenu
            groups={providerGroups}
            selectedModelId={selectedModelId}
            onValueChange={onValueChange}
          />
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    );
  }

  return (
    <Select.Root size="1" value={value} onValueChange={onValueChange}>
      <Select.Trigger className={styles.trigger} data-testid={ElementIds.MODEL_SELECTOR} variant="ghost">
        <Flex align="center">
          <Text size="1">{triggerLabel}</Text>
        </Flex>
      </Select.Trigger>
      <Select.Content position="popper" sideOffset={5}>
        {hasBackendModels ? (
          // A single pi provider renders its own provider-headed group.
          <ModelSelectOptions optionTestId={ElementIds.MODEL_OPTION} models={models} />
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

type CascadingProviderMenuProps = {
  groups: ReadonlyArray<{ provider: string; models: ReadonlyArray<ModelOption> }>;
  selectedModelId?: string;
  onValueChange: (next: string) => void;
};

/**
 * The dropdown body for a multi-provider backend catalog (pi): a top-level entry
 * per provider, each cascading into its own models.
 */
export const CascadingProviderMenu = ({
  groups,
  selectedModelId,
  onValueChange,
}: CascadingProviderMenuProps): ReactElement => (
  <>
    {groups.map((group) => (
      <DropdownMenu.Sub key={group.provider}>
        <DropdownMenu.SubTrigger data-testid={`${ElementIds.MODEL_PROVIDER_OPTION}-${group.provider}`}>
          {getProviderDisplayName(group.provider)}
        </DropdownMenu.SubTrigger>
        <DropdownMenu.SubContent>
          <DropdownMenu.RadioGroup value={selectedModelId ?? ""} onValueChange={onValueChange}>
            {group.models.map((option) => (
              <DropdownMenu.RadioItem
                key={option.modelId}
                value={option.modelId}
                data-testid={`${ElementIds.MODEL_OPTION}-${option.modelId}`}
              >
                {option.displayName}
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.SubContent>
      </DropdownMenu.Sub>
    ))}
  </>
);
