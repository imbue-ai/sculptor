import { CircleDot, Pencil, Trash2 } from "lucide-react";

import { ElementIds } from "../../../api";
import type { AgentAction, AgentActionRuntime } from "./types.ts";

/**
 * Single source of truth for agent context actions. Both the right-click
 * context menu (`<AgentContextMenuContent />`) and the command palette
 * (`agentActionsProvider` dynamic provider) consume this list.
 *
 * The Diagnostics submenu in the right-click menu is not represented
 * here — its items require an async API fetch on submenu open
 * (`getWorkspaceAgentDiagnostics`) and are still rendered inline by
 * `AgentContextMenuContent`. They are not surfaced in the command palette
 * for that reason.
 */
export const buildAgentActions = (runtime: AgentActionRuntime): ReadonlyArray<AgentAction> => [
  {
    id: "rename",
    title: "Rename",
    icon: Pencil,
    testId: ElementIds.TAB_CONTEXT_MENU_RENAME,
    paletteTitleSuffix: "name",
    perform: (agent): void => runtime.beginRename(agent),
  },
  {
    id: "mark_unread",
    title: "Mark unread",
    icon: CircleDot,
    testId: ElementIds.TAB_CONTEXT_MENU_MARK_UNREAD,
    paletteSubtitle: "Mark this agent as unread",
    perform: (agent): void => runtime.markUnread(agent),
  },
  {
    id: "delete",
    title: "Delete",
    icon: Trash2,
    destructive: true,
    separatorBefore: true,
    testId: ElementIds.TAB_CONTEXT_MENU_DELETE,
    paletteSubtitle: "Permanently delete this agent",
    paletteTitleSuffix: "name",
    perform: (agent): void => runtime.beginDelete(agent),
  },
];
