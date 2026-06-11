import { HomeIcon, PlusIcon, SettingsIcon } from "lucide-react";

import type { CommandRuntime } from "../runtime.ts";
import type { Command } from "../types.ts";

/**
 * Top-level navigation entries are *curated*, not registry-driven.
 *
 * The router (`Router.tsx`) owns several top-level paths — `/`, `/home`,
 * `/settings`, `/ws/:workspaceID`, `/component-gallery`, `/debug/*`. Most
 * of those deliberately do NOT get a Cmd+K row: workspace and agent
 * routes are surfaced by dynamic providers, /component-gallery and
 * /debug/* are dev-only. The "New workspace" entry below opens a modal
 * (it is NOT a navigation row).
 *
 * That means there is no useful "every route has a palette command"
 * drift test — a test like that would either be wrong (forcing palette
 * entries for routes that shouldn't have them) or curated by hand, in
 * which case the registry just tests itself. When you add a new
 * top-level route in `Router.tsx`, decide explicitly whether it
 * deserves a row here and add one if so.
 */
export const buildNavigationCommands = (runtime: CommandRuntime): Array<Command> => [
  // Naming convention across the palette:
  //   "Open X"      — direct navigation to a single concrete target.
  //   "Go to X..."  — pushes a sub-page so the user picks from a list.
  // These are the direct-nav entries; "Go to settings..." (page-opener
  // in builtinCommands/settings.ts) and "Go to workspace..." /
  // "Go to agent..." (dynamic providers) follow the same convention.
  {
    id: "nav.home",
    title: "Open home",
    subtitle: "Open the home page",
    keywords: ["dashboard", "start", "go to"],
    group: "navigation",
    icon: HomeIcon,
    shortcut: "home",
    // Slots after the lead picker (Go to workspace..., order 5) and
    // before Open settings (order 20) / Go to settings... (order 30).
    order: 10,
    perform: () => runtime.navigate.toHome(),
  },
  {
    id: "nav.settings",
    title: "Open settings",
    subtitle: "Application settings",
    keywords: ["preferences", "config", "options", "open", "go to"],
    group: "navigation",
    icon: SettingsIcon,
    shortcut: "settings",
    order: 20,
    perform: () => runtime.navigate.toSettings(),
  },
  {
    id: "nav.new_workspace",
    title: "New workspace",
    subtitle: "Create a workspace",
    keywords: ["create", "add"],
    // Lives in the Workspaces group (not Navigation) so the user finds
    // create / open / switch all in one place. `primary` + explicit
    // `order` keep it at the top of that group; the rest of the
    // ordering is set on the dynamic providers (workspaces.switch,
    // workspaces.actions.open, agents.switch, agents.actions.open).
    group: "workspaces",
    icon: PlusIcon,
    shortcut: "new_workspace",
    primary: true,
    order: 10,
    // Modal isn't a palette sub-page, but it's a doorway into a new
    // surface — the chevron signals that to the user the same way it
    // does for "Switch workspace…" / "Open settings…".
    showChevron: true,
    perform: () => runtime.modal.openNewWorkspaceFromPalette(),
  },
  {
    // Agent analog of nav.new_workspace: creates an agent in the current
    // workspace (inheriting the active agent's model) and navigates to it.
    // The action lives in `AgentTabs` (shared with the `+` button and the
    // `new_agent` keybinding) and is reached via `runtime.ui.createAgent`.
    // Gated on `activeWorkspaceId` because there's no workspace to add an
    // agent to on Home / Settings / the new-workspace flow.
    id: "nav.new_agent",
    title: "New agent",
    subtitle: "Create an agent in this workspace",
    keywords: ["create", "add", "task"],
    group: "workspaces",
    icon: PlusIcon,
    shortcut: "new_agent",
    primary: true,
    // Slots just after New workspace (10) and before the switch/open
    // dynamic providers (workspaces.switch, agents.switch, order 40+).
    order: 15,
    when: (ctx) => ctx.activeWorkspaceId != null,
    perform: () => runtime.ui.createAgent(),
  },
];
