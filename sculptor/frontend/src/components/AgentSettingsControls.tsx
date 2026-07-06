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
  /**
   * Hide the plan-mode toggle when the active harness can't honor a
   * mid-turn interactive backchannel (pi). Defaults to `true` so callsites
   * without a task yet (e.g. the new-workspace modal) show it.
   */
  canEnterPlanMode?: boolean;
  /**
   * Gate the fast-mode toggle on harness support in addition to the
   * model's own `supportsFastMode` capability. Defaults to `true`.
   */
  canUseFastMode?: boolean;
  /**
   * Gate the model picker on harness support. When false, the picker renders
   * disabled with a capability-tooltip. Defaults to `true`. Pi and registered
   * terminal agents set this to false because they manage their own model
   * catalogs; the Claude models pre-selected here do not apply.
   */
  canSelectModel?: boolean;
};

/**
 * The right-side toolbar block of agent settings — plan mode, fast mode
 * (when the model supports it), thinking effort, model. Lives standalone
 * so the new-workspace modal can render the same controls beneath its
 * prompt textarea without duplicating ChatInput's wiring. The fast-mode
 * toggle is gated on `getModelCapabilities(model).supportsFastMode`
 * here (rather than at every callsite) so consumers only have to pass
 * the selected model. The model picker is gated on `canSelectModel` so
 * harnesses that manage their own catalogs (pi, registered terminal agents)
 * can suppress the Claude model list.
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
  canEnterPlanMode = true,
  canUseFastMode = true,
  canSelectModel = true,
}: AgentSettingsControlsProps): ReactElement => {
  const { supportsFastMode: doesSupportFastMode } = getModelCapabilities(model);
  const { navigateToGlobalSettings } = useImbueNavigate();
  // ModelSelector's no-providers CTA (pi with an empty backend catalog) sends
  // the user to the pi login flow under Settings -> Pi, matching ChatInput.
  const handleAuthenticate = useCallback((): void => {
    navigateToGlobalSettings(SettingsSection.PI);
  }, [navigateToGlobalSettings]);
  return (
    <Flex align="center" flexShrink="0">
      {canEnterPlanMode && (
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
      )}
      {doesSupportFastMode && canUseFastMode && <FastModeToggle isActive={isFastMode} onToggle={onFastModeToggle} />}
      <EffortSelector effort={effort} onEffortChange={onEffortChange} />
      <Flex pr="1">
        <ModelSelector
          model={model}
          onModelChange={onModelChange}
          capabilityValue={canSelectModel}
          onAuthenticate={handleAuthenticate}
        />
      </Flex>
    </Flex>
  );
};
