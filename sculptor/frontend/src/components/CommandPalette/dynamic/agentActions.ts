import { SettingsIcon } from "lucide-react";

import { tasksArrayAtom } from "../../../common/state/atoms/tasks.ts";
import { buildAgentActions } from "../contextActions/agentActions.ts";
import { agentActionsTargetAtom } from "../contextActions/atoms.ts";
import type { AgentActionRuntime } from "../contextActions/types.ts";
import type { CommandRuntime } from "../runtime.ts";
import type { Command, DynamicProvider } from "../types.ts";

const taskDisplayTitle = (task: { title?: string | null; initialPrompt: string }): string => {
  const display = task.title?.trim() || task.initialPrompt.trim() || "Untitled agent";
  return display.length > 80 ? `${display.slice(0, 77)}...` : display;
};

/**
 * Surfaces the right-click menu actions for the CURRENT agent in Cmd+K.
 * Cross-agent action picking is intentionally not supported — the user
 * said agents follow the same scoping as workspace actions.
 *
 * Flow:
 *   "Agent actions…" (root, primary, only when ctx.activeAgentId)
 *      → agent.actions  (pick an action for the current agent)
 *
 * Diagnostics submenu items remain right-click-only — they require an
 * async API fetch on submenu open and don't fit the descriptor shape.
 */
export const buildAgentActionsProvider = (
  runtime: CommandRuntime,
  actionRuntime: AgentActionRuntime,
): DynamicProvider => ({
  id: "dynamic.agent_actions",
  produce: (ctx): Array<Command> => {
    if (ctx.activeAgentId == null || ctx.activeWorkspaceId == null) return [];
    const tasks = runtime.store.get(tasksArrayAtom) ?? [];
    const target = tasks.find((t) => t.id === ctx.activeAgentId);
    if (target == null) return [];

    const display = taskDisplayTitle(target);
    const actions = buildAgentActions(actionRuntime);
    const out: Array<Command> = [];

    out.push({
      id: "agents.actions.open",
      title: "Agent actions...",
      // Agent name leads the subtitle so it stays visible even when
      // the row gets truncated — same rationale as workspace actions.
      // Long agent titles are common (they default to the initial
      // prompt), so this matters in practice. Descriptor stays generic
      // because the action set will grow.
      subtitle: `${display} — actions for this agent`,
      keywords: ["rename", "delete", "unread", "manage", "edit", "task"],
      group: "workspaces",
      icon: SettingsIcon,
      pageId: "agent.actions",
      primary: true,
      order: 50,
      perform: () => {
        runtime.store.set(agentActionsTargetAtom, {
          workspaceId: ctx.activeWorkspaceId as string,
          agentId: target.id,
        });
      },
    });

    // Mechanical descriptor → Command projection. Per-action metadata
    // (title-suffix policy, extra keywords, etc.) lives on the descriptor
    // in `contextActions/agentActions.ts`. The agent's display name is
    // appended to keywords on every row so fuzzy search matches by name.
    for (const action of actions) {
      if (action.visible && !action.visible(target)) continue;
      const baseTitle = action.getTitle ? action.getTitle(target) : action.title;
      const titleSuffix = action.paletteTitleSuffix === "name" ? `: ${display}` : "";
      const isDisabled = action.disabled?.(target) ?? false;
      const reason = isDisabled ? action.disabledReason?.(target) : undefined;
      const baseSubtitle = action.getPaletteSubtitle ? action.getPaletteSubtitle(target) : action.paletteSubtitle;
      const baseKeywords = action.getPaletteKeywords ? action.getPaletteKeywords(target) : action.paletteKeywords;
      out.push({
        id: `agents.action.${target.id}.${action.id}`,
        title: `${baseTitle}${titleSuffix}`,
        // See workspaceActions.ts for the rationale — disabled rows
        // carry the reason inline so it's visible without hovering.
        subtitle: reason ?? baseSubtitle,
        keywords: [action.id, "agent", "task", ...(baseKeywords ?? []), display.toLowerCase()],
        group: "workspaces",
        icon: action.icon,
        shortcut: action.paletteShortcut,
        onPage: "agent.actions",
        order: action.paletteOrder,
        disabled: isDisabled,
        perform: () => action.perform(target),
      });
    }

    return out;
  },
});
