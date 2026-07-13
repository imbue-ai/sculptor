import { Flex, IconButton, Tooltip } from "@radix-ui/themes";
import { ListChecks } from "lucide-react";
import type { ReactElement } from "react";

import { type EffortLevel, ElementIds, type LlmModel } from "~/api";
import { getModelCapabilities } from "~/common/modelCapabilities.ts";
import { EffortSelector } from "~/components/EffortSelector.tsx";
import { FastModeToggle } from "~/components/FastModeToggle.tsx";
import { ModelSelector } from "~/components/ModelSelector.tsx";

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
 * This block is Claude-only: the new-workspace modal renders it beneath its
 * prompt textarea for a Claude first agent. The other harnesses don't consume
 * these controls at create — pi drives its own backend-sourced model picker in
 * the modal (a separate block), and terminal/registered agents have no model —
 * so the modal chooses the block by agent type rather than gating these controls
 * one by one. The fast-mode toggle is gated on
 * `getModelCapabilities(model).supportsFastMode` here (rather than at every
 * callsite) so consumers only have to pass the selected model.
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
        <ModelSelector model={model} onModelChange={onModelChange} />
      </Flex>
    </Flex>
  );
};
