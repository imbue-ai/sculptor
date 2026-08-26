import { ArrowLeftIcon, ArrowRightIcon, BotIcon } from "lucide-react";

import type { CommandRuntime } from "../runtime.ts";
import type { Command } from "../types.ts";

/**
 * Workspace and agent navigation commands. Each command wraps an existing
 * keybinding (next_tab, previous_tab, next_agent, previous_agent) so the
 * binding is a single source of truth — the shortcut hint shown in the
 * palette is whatever the user has remapped to.
 *
 * Workspace navigation lives on the `workspace.actions` sub-page; agent
 * navigation lives on `agents.switch` (next to the agent list) so
 * picking an agent and stepping through agents share one entry-point.
 * They still surface at root via fuzzy search (and via their
 * keybindings), so this scoping does NOT make them harder to invoke.
 */
export const buildWorkspaceActionCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "workspaces.next_tab",
    title: "Next workspace",
    subtitle: "Switch to the next workspace",
    keywords: ["workspace", "tab", "switch", "cycle"],
    group: "workspaces",
    icon: ArrowRightIcon,
    shortcut: "next_tab",
    onPage: "workspace.actions",
    // Slots after Rename (50) on the workspace.actions sub-page — see
    // `dynamic/workspaceActions.ts` for the full sequence.
    order: 60,
    perform: () => runtime.ui.nextWorkspaceTab(),
  },
  {
    id: "workspaces.previous_tab",
    title: "Previous workspace",
    subtitle: "Switch to the previous workspace",
    keywords: ["workspace", "tab", "switch", "cycle"],
    group: "workspaces",
    icon: ArrowLeftIcon,
    shortcut: "previous_tab",
    onPage: "workspace.actions",
    order: 70,
    perform: () => runtime.ui.previousWorkspaceTab(),
  },
  {
    id: "agents.next",
    title: "Next agent",
    subtitle: "Switch to the agent on the right",
    keywords: ["task", "switch", "cycle"],
    group: "workspaces",
    icon: BotIcon,
    shortcut: "next_agent",
    onPage: "agents.switch",
    perform: () => runtime.ui.nextAgent(),
  },
  {
    id: "agents.previous",
    title: "Previous agent",
    subtitle: "Switch to the agent on the left",
    keywords: ["task", "switch", "cycle"],
    group: "workspaces",
    icon: BotIcon,
    shortcut: "previous_agent",
    onPage: "agents.switch",
    perform: () => runtime.ui.previousAgent(),
  },
];
