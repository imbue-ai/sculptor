import type { PluginHostApi, ToolCallView } from "@sculptor/plugin-sdk";
import { GitFork } from "lucide-react";

import { parseWorkflowInput } from "./parseWorkflow.ts";
import { WorkflowBody } from "./WorkflowBody.tsx";

/**
 * A reference tool visualization: it replaces the generic rendering of Claude
 * Code's `Workflow` tool with the workflow's name, a phase checklist, and its
 * result. It is the worked example other tool-visualization plugins copy.
 */

/** The `meta` line for a running or completed call — a phase count or the run status. */
const summaryMeta = (call: ToolCallView, phaseCount: number): string => {
  if (call.result !== null) return call.result.isError ? "failed" : "done";
  if (call.status === "running") return "running";
  if (phaseCount > 0) return `${phaseCount} ${phaseCount === 1 ? "phase" : "phases"}`;
  return "workflow";
};

export default function activate(api: PluginHostApi): () => void {
  return api.registerToolVisualization({
    id: "workflow-viz",
    toolNames: ["Workflow"],
    agentTypes: ["claude"],
    // A result-only block (`input === null`) still renders — the body shows the
    // result. Otherwise only claim inputs the parser recognizes as a workflow,
    // so unrecognized shapes fall through to stock rendering.
    canRender: (call) => call.input === null || parseWorkflowInput(call.input) !== null,
    icon: GitFork,
    summary: (call) => {
      const parsed = parseWorkflowInput(call.input);
      return {
        title: parsed?.name ?? "workflow",
        meta: summaryMeta(call, parsed?.phases.length ?? 0),
      };
    },
    body: WorkflowBody,
  });
}
