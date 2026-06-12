import { ArrowUpRight, BotIcon } from "lucide-react";

import { tasksArrayAtom } from "../../../common/state/atoms/tasks.ts";
import type { CommandRuntime } from "../runtime.ts";
import type { Command, DynamicProvider } from "../types.ts";

const taskDisplayTitle = (task: { title?: string | null; initialPrompt: string }): string => {
  const display = task.title?.trim() || task.initialPrompt.trim() || "Untitled agent";
  return display.length > 80 ? `${display.slice(0, 77)}...` : display;
};

/**
 * Surfaces agents in the palette, scoped to the workspace the user is
 * currently viewing. Cross-workspace switching is intentionally not
 * supported: the user said "we only need to be able to switch between
 * agents in the current workspace" — every other entry-point either
 * cluttered the root list or made the flow slower.
 *
 * Flow:
 *   "Switch agent…" (root, primary)  →  agents.switch sub-page  →  one
 *   row per agent in the current workspace.
 *
 * The entry stays visible (greyed-out) when the workspace has 0 or 1
 * agents, so the user knows the capability exists; we just disable
 * selection so they don't enter an empty sub-page. Hidden entirely when
 * there is no current workspace (Home / Settings), where the concept
 * doesn't apply.
 */
export const buildAgentProvider = (runtime: CommandRuntime): DynamicProvider => ({
  id: "dynamic.agents",
  produce: (ctx): Array<Command> => {
    if (ctx.activeWorkspaceId == null) return [];
    const tasks = runtime.store.get(tasksArrayAtom) ?? [];
    const inWorkspace = tasks
      .filter((t) => t.workspaceId === ctx.activeWorkspaceId)
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

    const hasMultipleAgents = inWorkspace.length >= 2;
    const subtitle =
      inWorkspace.length === 0
        ? "No other agents in this workspace"
        : inWorkspace.length === 1
          ? "Only one agent in this workspace"
          : `${inWorkspace.length} agents in this workspace`;

    const out: Array<Command> = [
      {
        id: "agents.switch",
        title: "Go to agent...",
        subtitle,
        keywords: ["task", "switch", "open", "jump"],
        group: "workspaces",
        // Shared "Go to ..." page-opener icon (mirrors workspaces.switch).
        // The per-agent child rows below keep BotIcon to stay
        // recognisably "agent" rows on the sub-page.
        icon: ArrowUpRight,
        pageId: "agents.switch",
        primary: true,
        order: 40,
        disabled: !hasMultipleAgents,
        perform: (): void => {
          // Page push handled by the runner.
        },
      },
    ];

    if (!hasMultipleAgents) return out;

    for (const task of inWorkspace) {
      const display = taskDisplayTitle(task);
      const isCurrent = ctx.activeAgentId === task.id;
      out.push({
        id: `agents.page.${task.id}`,
        title: display,
        subtitle: isCurrent ? "Current agent" : undefined,
        keywords: ["agent", "task", "go to"],
        group: "workspaces",
        icon: BotIcon,
        onPage: "agents.switch",
        disabled: isCurrent,
        disabledReason: isCurrent ? "Already on this agent" : undefined,
        perform: () => runtime.navigate.toAgent(ctx.activeWorkspaceId as string, task.id),
      });
    }

    return out;
  },
});
