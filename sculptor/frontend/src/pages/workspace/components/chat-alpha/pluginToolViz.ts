import { useAtomValue } from "jotai";
import { useMemo } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { isGenericToolContent } from "~/common/Guards.ts";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { encodeRegisteredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { taskAtomFamily } from "~/common/state/atoms/tasks.ts";
import type { PluginToolVisualization } from "~/plugins/pluginRegistry.ts";
import { pluginToolVisualizationsAtom } from "~/plugins/pluginRegistry.ts";
import type { ToolCallStatus, ToolCallView, ToolVisualizationDefinition } from "~/plugins/types.ts";

import type { PillState } from "./toolPill.types.ts";

/** Map a pill's lifecycle state to the plugin-facing tool-call status. */
const statusFromPillState = (state: PillState): ToolCallStatus => {
  if (state === "initializing") return "running";
  if (state === "error") return "error";
  return "success";
};

// The extractor DefaultEntry uses to stringify a tool result — GenericToolContent
// carries the text; a DiffToolContent (diff tools are routed to the chip row well
// before pills) has none, so it stringifies to empty.
const resultText = (result: ToolResultBlock | null): string => {
  if (!result) return "";
  if (isGenericToolContent(result.content)) return result.content.text;
  return "";
};

/**
 * Build the curated {@link ToolCallView} a plugin visualizer sees from a paired
 * tool_use block / result. `block` is null for result-only pills (input is then
 * null); `result` is null while the call is still running. `agentType` is the
 * stored encoding of the owning task's harness, or null when unknown.
 */
export const buildToolCallView = (inputs: {
  block: ToolUseBlock | null;
  result: ToolResultBlock | null;
  pillState: PillState;
  agentType: string | null;
}): ToolCallView => {
  const { block, result, pillState, agentType } = inputs;
  const id = block?.id ?? result?.toolUseId ?? "";
  const toolName = block?.name ?? result?.toolName ?? "";
  const invocation = (block?.invocationString as string | undefined) ?? result?.invocationString ?? null;
  return {
    id,
    toolName,
    agentType,
    input: block?.input ?? null,
    status: statusFromPillState(pillState),
    invocation,
    result: result ? { text: resultText(result), isError: result.isError ?? false } : null,
    durationSeconds: result?.durationSeconds ?? null,
  };
};

/**
 * Pick the tool-visualization registration that should render `call`, or null
 * for none. Candidates are registrations whose `toolNames` contains the call's
 * tool name (exact match). They are then filtered by `agentTypes` (a scoped
 * registration never matches a null/unknown `agentType`; an unscoped one always
 * does) and by `canRender` (missing = eligible; a throw is treated as declined).
 * Among survivors, the last-registered wins — so the array is scanned in
 * reverse, consistent with replace-by-id semantics elsewhere.
 */
export const selectToolVisualization = (
  defs: ReadonlyArray<PluginToolVisualization>,
  call: ToolCallView,
): PluginToolVisualization | null => {
  for (let i = defs.length - 1; i >= 0; i--) {
    const candidate = defs[i];
    const { definition } = candidate;
    if (!definition.toolNames.includes(call.toolName)) continue;
    if (definition.agentTypes !== undefined) {
      if (call.agentType === null) continue;
      if (!definition.agentTypes.includes(call.agentType)) continue;
    }

    if (definition.canRender) {
      let isAllowed: boolean;
      try {
        isAllowed = definition.canRender(call);
      } catch {
        // `canRender` is untrusted: a throw declines this candidate rather than
        // taking down the row, so the next candidate (or built-in) still renders.
        continue;
      }
      if (!isAllowed) continue;
    }
    return candidate;
  }
  return null;
};

/**
 * The summary a visualizer contributes for `call`, or null to fall back to the
 * host's default title. `summary` is untrusted: a throw is treated as declined
 * (null), so a broken summarizer never takes down the row — it just reverts to
 * the stock title/meta.
 */
export const safeSummary = (
  definition: ToolVisualizationDefinition,
  call: ToolCallView,
): { title: string; meta?: string } | null => {
  if (!definition.summary) return null;
  try {
    return definition.summary(call);
  } catch {
    return null;
  }
};

/**
 * The stored agent-type encoding for the workspace's current task
 * (`registered:<id>` for registered agents), or null when the task or its agent
 * type is unknown. Drives the `agentTypes` filter in tool-visualization dispatch.
 */
export const useCurrentTaskAgentType = (): string | null => {
  const { agentID } = useWorkspacePageParams();
  const task = useAtomValue(taskAtomFamily(agentID ?? ""));
  if (!task || task.agentType == null) return null;
  if (task.agentType === "registered") {
    // A registered agent with no registration id can't be addressed distinctly,
    // so it stays unknown rather than matching a bare "registered" scope.
    return task.registrationId ? encodeRegisteredAgentType(task.registrationId) : null;
  }
  return task.agentType;
};

/**
 * The tool-visualization registration that should render this tool call, or
 * null. Reads the plugin registry and the current task's agent type, builds the
 * curated {@link ToolCallView}, and dispatches. Memoized so the (hot) chat
 * render path doesn't re-scan the registry unless its inputs change.
 */
export const usePluginToolVisualization = (inputs: {
  block: ToolUseBlock | null;
  result: ToolResultBlock | null;
  pillState: PillState;
}): { visualization: PluginToolVisualization | null; call: ToolCallView } => {
  const { block, result, pillState } = inputs;
  const defs = useAtomValue(pluginToolVisualizationsAtom);
  const agentType = useCurrentTaskAgentType();

  const call = useMemo(
    () => buildToolCallView({ block, result, pillState, agentType }),
    [block, result, pillState, agentType],
  );
  const visualization = useMemo(() => selectToolVisualization(defs, call), [defs, call]);
  return { visualization, call };
};
