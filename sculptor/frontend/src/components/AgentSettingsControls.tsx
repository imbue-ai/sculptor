import { Flex, IconButton, Tooltip } from "@radix-ui/themes";
import { ListChecks } from "lucide-react";
import { type ReactElement, useCallback } from "react";

import { type EffortLevel, ElementIds, type LlmModel } from "~/api";
import { getModelCapabilities } from "~/common/modelCapabilities.ts";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { EffortSelector } from "~/components/EffortSelector.tsx";
import { FastModeToggle } from "~/components/FastModeToggle.tsx";
import { ModelSelector } from "~/components/ModelSelector.tsx";
import { SettingsSection } from "~/pages/settings/sections.ts";

type AgentSettingsControlsProps = {
  model: LlmModel;
  onModelChange: (model: LlmModel) => void;
  effort: EffortLevel;
  onEffortChange: (effort: EffortLevel) => void;
  isFastMode: boolean;
  onFastModeToggle: () => void;
  isPlanMode: boolean;
  onPlanModeToggle: () => void;
};

/**
 * The right-side toolbar block of a Claude first agent's per-prompt settings —
 * plan mode, fast mode (when the model supports it), thinking effort, and model.
 * The new-workspace modal renders this beneath its prompt textarea for a Claude
 * first agent. Non-Claude harnesses don't consume any of these at create (pi
 * picks its model from its own in-task catalog and plans from the chat; terminal
 * agents have no model), so the modal renders its own hint in place of this
 * block rather than gating the controls one by one. The fast-mode toggle is
 * gated on `getModelCapabilities(model).supportsFastMode` here (rather than at
 * every callsite) so consumers only have to pass the selected model.
 *
 * ChatInput renders a parallel copy of this toolbar block that adds
 * capability-gated disabled states and a backend-model selector it needs in
 * the live chat. Keep the shared tooltip strings, aria-labels, testids, and
 * styling here in sync with that copy.
 */
export const AgentSettingsControls = ({
  model,
  onModelChange,
  effort,
  onEffortChange,
  isFastMode,
  onFastModeToggle,
  isPlanMode,
  onPlanModeToggle,
}: AgentSettingsControlsProps): ReactElement => {
  const { supportsFastMode: doesSupportFastMode } = getModelCapabilities(model);
  const { navigateToGlobalSettings } = useImbueNavigate();
  // ModelSelector requires an authenticate handler for its no-providers CTA. That
  // CTA is a pi-only state that never fires for this Claude cluster, but the prop
  // is required, so route it to the pi login flow to match ChatInput.
  const handleAuthenticate = useCallback((): void => {
    navigateToGlobalSettings(SettingsSection.PI);
  }, [navigateToGlobalSettings]);
  return (
    <Flex align="center" flexShrink="0">
      <Tooltip content={isPlanMode ? "Leave plan mode" : "Enter plan mode"}>
        <IconButton
          variant="ghost"
          size="3"
          onClick={onPlanModeToggle}
          aria-label="Toggle plan first mode"
          data-testid={ElementIds.PLAN_MODE_TOGGLE}
          data-active={isPlanMode}
          style={isPlanMode ? { color: "var(--button-primary-bg)", margin: 0 } : { margin: 0 }}
        >
          <ListChecks size={16} />
        </IconButton>
      </Tooltip>
      {doesSupportFastMode && <FastModeToggle isActive={isFastMode} onToggle={onFastModeToggle} />}
      <EffortSelector effort={effort} onEffortChange={onEffortChange} />
      <Flex pr="1">
        <ModelSelector model={model} onModelChange={onModelChange} onAuthenticate={handleAuthenticate} />
      </Flex>
    </Flex>
  );
};
