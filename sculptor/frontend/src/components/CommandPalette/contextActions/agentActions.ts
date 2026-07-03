import { CircleDot, Trash2 } from "lucide-react";

import { ElementIds } from "../../../api";
import type { AgentAction, AgentActionRuntime } from "./types.ts";

/**
 * Single source of truth for the command palette's agent actions, consumed by
 * the `agentActionsProvider` dynamic provider. The agent panel-tab's
 * right-click menu builds its own item list (see `dynamicPanels.tsx`) because
 * its extra entries — the copy/diagnostics items — depend on per-agent
 * diagnostics fetched outside the palette; those are not surfaced here.
 *
 * Rename is intentionally absent: agent rename is the panel tab's inline edit
 * (local state in `SectionHeader`), which the palette runtime has no way to
 * trigger. Don't add a rename descriptor here without wiring a real rename
 * flow behind it — a descriptor whose perform goes nowhere still renders as a
 * selectable palette row.
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
