import { BugIcon, KeyboardIcon } from "lucide-react";

import type { Command } from "../types/commandPalette.ts";
import type { CommandRuntime } from "../utils/runtime.ts";

export const buildHelpCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "help.shortcuts",
    title: "Show keyboard shortcuts",
    subtitle: "Open the shortcut reference",
    keywords: ["hotkeys", "bindings", "help", "docs"],
    group: "help",
    icon: KeyboardIcon,
    shortcut: "help",
    perform: () => runtime.ui.toggleHelpDialog(),
  },
  {
    id: "help.report_problem",
    title: "Report a problem",
    subtitle: "File a bug or send feedback",
    keywords: ["bug", "feedback", "issue", "file", "diagnostics"],
    group: "help",
    icon: BugIcon,
    perform: () => runtime.ui.openReportProblem(),
  },
];
