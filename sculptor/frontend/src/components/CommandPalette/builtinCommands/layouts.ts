import { LayoutTemplate, Plus } from "lucide-react";

import type { CommandRuntime } from "../runtime.ts";
import type { Command } from "../types.ts";

// Static Layouts commands: the "Layouts…" opener (carries the ⌘⇧L hint) and the
// "Save current arrangement as layout…" shortcut. The per-layout "Switch to X"
// rows are dynamic — see dynamic/layouts.ts. Both are gated on a workspace being
// active, since a layout applies to the current workspace's arrangement.
export const buildLayoutCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "layouts.save",
    title: "Save current arrangement as layout…",
    subtitle: "New layout from this workspace",
    keywords: ["layout", "save", "capture", "arrangement"],
    group: "layouts",
    icon: Plus,
    order: 100,
    when: (ctx) => ctx.activeWorkspaceId != null,
    perform: () => runtime.openSaveLayoutModal(),
  },
  {
    id: "layouts.open",
    title: "Layouts…",
    subtitle: "Switch, save, and manage layouts",
    keywords: ["layout", "switch", "arrangement", "manage"],
    group: "layouts",
    icon: LayoutTemplate,
    // Shows the ⌘⇧L hint and, on select, closes the palette and opens the switcher.
    shortcut: "open_layouts",
    order: 110,
    when: (ctx) => ctx.activeWorkspaceId != null,
    perform: () => runtime.openLayoutsModal(),
  },
];
