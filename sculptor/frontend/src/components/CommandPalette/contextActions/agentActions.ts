import { CircleDot, Pencil, Trash2 } from "lucide-react";

import { ElementIds } from "../../../api";
import type { AgentAction, AgentActionRuntime } from "./types.ts";

/**
 * Single source of truth for the command palette's agent actions, consumed by
 * the `agentActionsProvider` dynamic provider. The agent panel-tab's
 * right-click menu builds its own item list (see `dynamicPanels.tsx`) because
 * its extra entries — the copy/diagnostics items — depend on per-agent
 * diagnostics fetched outside the palette; those are not surfaced here.
 *
 * Rename routes through the panel tab's inline edit: its `perform` calls
 * `runtime.beginRename`, which activates the agent's panel and stashes a
 * rename handoff that the palette flushes to `agentRenameTargetAtom` once its
 * dialog has closed (see `palettePendingRenameAtom`), so the mounted tab in
 * `SectionHeader` enters its existing inline-rename mode. Reusing that path
 * keeps the single optimistic rename mutation and avoids a forked dialog.
 */
export const buildAgentActions = (runtime: AgentActionRuntime): ReadonlyArray<AgentAction> => [
  {
    id: "mark_unread",
    title: "Mark as unread",
    icon: CircleDot,
    testId: ElementIds.TAB_CONTEXT_MENU_MARK_UNREAD,
    paletteSubtitle: "Mark this agent as unread",
    perform: (agent): void => runtime.markUnread(agent),
  },
  {
    id: "rename",
    title: "Rename",
    icon: Pencil,
    separatorBefore: true,
    testId: ElementIds.TAB_CONTEXT_MENU_RENAME,
    paletteOrder: 50,
    paletteTitleSuffix: "name",
    perform: (agent): void => runtime.beginRename(agent),
  },
  {
    id: "delete",
    title: "Delete",
    icon: Trash2,
    destructive: true,
    separatorBefore: true,
    testId: ElementIds.TAB_CONTEXT_MENU_DELETE,
    paletteSubtitle: "Permanently delete this agent",
    paletteOrder: 110,
    paletteTitleSuffix: "name",
    perform: (agent): void => runtime.beginDelete(agent),
  },
];
