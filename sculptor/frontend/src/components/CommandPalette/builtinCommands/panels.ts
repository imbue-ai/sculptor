import {
  EyeIcon,
  LayoutPanelLeftIcon,
  PanelBottomIcon,
  PanelLeftIcon,
  PanelRightIcon,
  PuzzleIcon,
  ScanLine,
} from "lucide-react";

import type { CommandRuntime } from "../runtime.ts";
import type { Command } from "../types.ts";

// View is split into two sub-pages so the root list isn't dominated by
// 10+ "Toggle X" rows: layout-level toggles (panel zones + Focus/Zen
// modes) live on `view.layout`; individual panel toggles (Files,
// Actions, Terminal, …) live on `view.panels`. The `view.panels` page
// title intentionally matches what users search for ("Toggle panel
// visibility...") so typing it surfaces the page that actually lists
// panels.
export const buildPanelCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "view.toggle_layout",
    title: "Toggle layout...",
    subtitle: "Show or hide the left, right, or bottom zone; or use Focus / Zen mode",
    keywords: ["layout", "zone", "sidebar", "visibility", "show", "hide", "view", "focus", "zen"],
    group: "view",
    icon: LayoutPanelLeftIcon,
    pageId: "view.layout",
    primary: true,
    // Sits below theme entries (order 10/20) within the merged
    // Theme & Layout group; layout-zone toggles lead, panel-visibility
    // follows.
    order: 100,
    when: (ctx) => ctx.route.isWorkspace,
    perform: (): void => {
      // Page push handled by the runner.
    },
  },
  {
    id: "view.toggle_panels",
    title: "Toggle panel visibility...",
    subtitle: "Show or hide individual panels (Files, Actions, Terminal, …)",
    keywords: ["panel", "visibility", "show", "hide", "view", "tool"],
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
  // Zone toggles + the two display modes. The `when` guard is kept on
  // each row even though the entry-point already gates on workspace,
  // so deep-linking / direct keybinding still respects route.
  //
  // Explicit `order` so the row sequence reads zone-toggles first
  // (Bottom → Left → Right), then the two display modes (Focus,
  // then Zen — Zen is the most extreme so it sits at the bottom).
  // Alphabetical alone would interleave Focus between Bottom and
  // Left, which broke the mental grouping.
  {
    id: "view.toggle_bottom_panel",
    title: "Toggle bottom panel",
    subtitle: "Show or hide the bottom panel",
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
    subtitle: "Show or hide the left sidebar",
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
    subtitle: "Show or hide the right sidebar",
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
    id: "view.focus_mode",
    title: "Toggle focus mode",
    subtitle: "Hide all panels for distraction-free chat",
    keywords: ["minimize", "hide"],
    group: "view",
    // Matches the Focus Mode toggle in the BottomBar so the visual
    // language is consistent across surfaces.
    icon: ScanLine,
    shortcut: "focus_mode",
    onPage: "view.layout",
    order: 40,
    when: (ctx) => ctx.route.isWorkspace,
    perform: () => runtime.ui.toggleFocusMode(),
  },
  {
    id: "view.zen_mode",
    title: "Toggle zen mode",
    subtitle: "Maximize chat by hiding all UI chrome",
    keywords: ["fullscreen", "distraction"],
    group: "view",
    icon: EyeIcon,
    shortcut: "zen_mode",
    onPage: "view.layout",
    order: 50,
    when: (ctx) => ctx.route.isWorkspace,
    perform: () => runtime.ui.toggleZenMode(),
  },
];
