import { Trash2Icon } from "lucide-react";

import type { CommandRuntime } from "../runtime.ts";
import type { Command } from "../types.ts";

export const buildTerminalCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "terminal.clear",
    title: "Clear terminal",
    subtitle: "Wipe the active terminal's screen and scrollback",
    keywords: ["wipe", "reset", "clean", "scrollback", "console"],
    group: "terminal",
    icon: Trash2Icon,
    shortcut: "clear_terminal",
    when: (ctx) => ctx.hasTerminalPanel,
    perform: () => runtime.ui.clearActiveTerminal(),
  },
];
