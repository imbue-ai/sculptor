import {
  LayoutPanelLeftIcon,
  Maximize2,
  Menu,
  Minimize2,
  PanelBottomIcon,
  PanelLeftIcon,
  PanelRightIcon,
  PuzzleIcon,
} from "lucide-react";

import type { CommandRuntime } from "../runtime.ts";
import type { Command, CommandIcon } from "../types.ts";

// The Panels & Sections group is split into two sub-pages so the root list
// isn't dominated by 10+ per-panel rows: section toggles (the
// left/right/bottom sections) live on `view.layout`; individual "Show X"
// panel reveals (Files, Actions, Terminal, …) live on `view.panels`. The
// `view.panels` page title intentionally matches what users search for
// ("Show panel...") so typing it surfaces the page that actually lists
// panels.
export const buildPanelCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "view.toggle_layout",
    title: "Toggle sections...",
    subtitle: "Show or hide the left, right, or bottom section",
    keywords: ["layout", "section", "sidebar", "visibility", "show", "hide", "view"],
    group: "panels",
    icon: LayoutPanelLeftIcon,
    pageId: "view.layout",
    primary: true,
    // Within Panels & Sections: Add panel (90) leads, then section
    // toggles, then panel-visibility.
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
    group: "panels",
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
    title: "Toggle bottom section",
    subtitle: "Show or hide the bottom section",
    keywords: ["console", "terminal", "panel"],
    group: "panels",
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
    title: "Toggle left section",
    subtitle: "Show or hide the left section",
    // "sidebar" is deliberately absent: the product vocabulary reserves it for
    // the nav rail toggle (view.toggle_sidebar), so a "sidebar" search lands
    // there rather than on the workspace sections.
    keywords: ["left", "panel"],
    group: "panels",
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
    title: "Toggle right section",
    subtitle: "Show or hide the right section",
    keywords: ["right", "panel"],
    group: "panels",
    icon: PanelRightIcon,
    shortcut: "toggle_right_panel",
    onPage: "view.layout",
    order: 30,
    when: (ctx) => ctx.route.isWorkspace,
    perform: () => runtime.ui.toggleRightPanel(),
    keepOpen: true,
  },
  // The sidebar is workspace-navigation chrome rather than a section, so its
  // toggle lives in the Navigation group at the root (not on the sections
  // sub-page). It is deliberately NOT route-gated: the sidebar rail renders on
  // every route (workspace, Home, Settings), so the toggle must too.
  {
    id: "view.toggle_sidebar",
    title: "Toggle sidebar",
    subtitle: "Collapse or expand the workspace sidebar",
    keywords: ["sidebar", "nav", "navigation", "workspaces", "rail", "collapse", "expand"],
    group: "navigation",
    // The nav rail is navigation chrome, not a section, so it gets the menu
    // glyph rather than a panel icon — lucide's `Sidebar` is an alias of
    // `PanelLeft`, which would render identically to the left-section toggle.
    icon: Menu,
    shortcut: "toggle_sidebar",
    order: 100,
    perform: () => runtime.ui.toggleSidebar(),
    keepOpen: true,
  },
  {
    id: "view.maximize_section",
    // Stable title for fuzzy-search ranking; the keywords carry the
    // "minimize" vocabulary so the row is findable in both states, and
    // `getTitle`/`getSubtitle`/`getIcon` flip the display copy while a
    // section is maximized (the command toggles, so the copy should name
    // the action it will actually perform).
    title: "Maximize section",
    subtitle: "Maximize the active section, or restore if already maximized",
    keywords: ["maximize", "minimize", "fullscreen", "expand", "restore", "section", "focus"],
    group: "panels",
    icon: Maximize2,
    getTitle: (ctx): string => (ctx.isSectionMaximized ? "Minimize section" : "Maximize section"),
    getSubtitle: (ctx): string =>
      ctx.isSectionMaximized ? "Restore the maximized section to the normal layout" : "Maximize the active section",
    getIcon: (ctx): CommandIcon => (ctx.isSectionMaximized ? Minimize2 : Maximize2),
    shortcut: "maximize_section",
    onPage: "view.layout",
    order: 50,
    when: (ctx) => ctx.route.isWorkspace,
    // Closes the palette (no keepOpen) so the maximized section is visible immediately.
    perform: () => runtime.ui.toggleMaximizeSection(),
  },
];
