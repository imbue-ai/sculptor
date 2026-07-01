import {
  LayoutPanelLeftIcon,
  Maximize2,
  PanelBottomIcon,
  PanelLeftIcon,
  PanelRightIcon,
  PuzzleIcon,
  Sidebar,
} from "lucide-react";

import type { CommandRuntime } from "../runtime.ts";
import type { Command } from "../types.ts";

// View is split into two sub-pages so the root list isn't dominated by
// 10+ "Toggle X" rows: layout-level toggles (the left/right/bottom
// sections) live on `view.layout`; individual panel toggles (Files,
// Actions, Terminal, …) live on `view.panels`. The `view.panels` page
// title intentionally matches what users search for ("Toggle panel
// visibility...") so typing it surfaces the page that actually lists
// panels.
export const buildPanelCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "view.toggle_layout",
    title: "Toggle layout...",
    subtitle: "Show or hide the left, right, or bottom section",
    keywords: ["layout", "section", "sidebar", "visibility", "show", "hide", "view"],
    group: "view",
    icon: LayoutPanelLeftIcon,
    pageId: "view.layout",
    primary: true,
    // Sits below theme entries (order 10/20) within the merged
    // Theme & Layout group; layout-section toggles lead, panel-visibility
    // follows.
    order: 100,
    when: (ctx) => ctx.route.isWorkspace,
    perform: (): void => {
      // Page push handled by the runner.
    },
  },
  {
    id: "view.toggle_panels",
    title: "Show panel...",
    subtitle: "Focus a panel already open in a section",
    keywords: ["panel", "visibility", "show", "focus", "reveal", "view", "tool"],
    group: "view",
    icon: PuzzleIcon,
    pageId: "view.panels",
    primary: true,
    order: 110,
    when: (ctx) => ctx.route.isWorkspace,
    perform: (): void => {
      // Page push handled by the runner.
    },
  },

  // ── view.layout sub-page ────────────────────────────────────────────
  // Section toggles. The `when` guard is kept on
  // each row even though the entry-point already gates on workspace,
  // so deep-linking / direct keybinding still respects route.
  //
  // Explicit `order` so the row sequence reads Bottom → Left → Right.
  {
    id: "view.toggle_bottom_panel",
    title: "Toggle bottom panel",
    subtitle: "Show or hide the bottom section",
    keywords: ["console", "terminal"],
    group: "view",
    icon: PanelBottomIcon,
    shortcut: "toggle_bottom_panel",
    onPage: "view.layout",
    order: 10,
    when: (ctx) => ctx.route.isWorkspace,
    perform: () => runtime.ui.toggleBottomPanel(),
    keepOpen: true,
  },
  {
    id: "view.toggle_left_panel",
    title: "Toggle left panel",
    subtitle: "Show or hide the left section",
    keywords: ["sidebar"],
    group: "view",
    icon: PanelLeftIcon,
    shortcut: "toggle_left_panel",
    onPage: "view.layout",
    order: 20,
    when: (ctx) => ctx.route.isWorkspace,
    perform: () => runtime.ui.toggleLeftPanel(),
    keepOpen: true,
  },
  {
    id: "view.toggle_right_panel",
    title: "Toggle right panel",
    subtitle: "Show or hide the right section",
    keywords: ["sidebar"],
    group: "view",
    icon: PanelRightIcon,
    shortcut: "toggle_right_panel",
    onPage: "view.layout",
    order: 30,
    when: (ctx) => ctx.route.isWorkspace,
    perform: () => runtime.ui.toggleRightPanel(),
    keepOpen: true,
  },
  {
    id: "view.toggle_sidebar",
    title: "Toggle sidebar",
    subtitle: "Collapse or expand the workspace sidebar",
    keywords: ["sidebar", "nav", "navigation", "workspaces", "rail", "collapse", "expand"],
    group: "view",
    icon: Sidebar,
    shortcut: "toggle_sidebar",
    onPage: "view.layout",
    order: 40,
    when: (ctx) => ctx.route.isWorkspace,
    perform: () => runtime.ui.toggleSidebar(),
    keepOpen: true,
  },
  {
    id: "view.maximize_section",
    title: "Maximize section",
    subtitle: "Maximize the active section, or restore if already maximized",
    keywords: ["maximize", "fullscreen", "expand", "restore", "section", "focus"],
    group: "view",
    icon: Maximize2,
    shortcut: "maximize_section",
    onPage: "view.layout",
    order: 50,
    when: (ctx) => ctx.route.isWorkspace,
    // Closes the palette (no keepOpen) so the maximized section is visible immediately.
    perform: () => runtime.ui.toggleMaximizeSection(),
  },
];
