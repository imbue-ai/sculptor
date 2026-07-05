import { ArrowDownIcon, MessageSquareIcon, Rows3Icon, RowsIcon, SearchIcon } from "lucide-react";

import { chatToolDensityAtom } from "~/pages/workspace/chatAlpha/atoms.ts";

import type { CommandRuntime } from "../runtime.ts";
import type { Command, CommandIcon } from "../types.ts";

export const buildChatCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "chat.focus_input",
    title: "Focus chat input",
    subtitle: "Move keyboard focus to the chat box",
    keywords: ["compose", "type"],
    group: "chat",
    icon: MessageSquareIcon,
    shortcut: "focus_input",
    // Only show on surfaces where there's actually a chat input to
    // focus. The `focus_input` keybinding (in
    // useGlobalKeyboardShortcuts) covers the AddWorkspace name
    // input as a separate, keyboard-only fallback — but the palette
    // row's title says "Focus chat input", so it must not surface
    // anywhere a chat input doesn't exist.
    when: (ctx) => ctx.hasChatPanel,
    perform: () => runtime.ui.focusChatInput(),
  },
  {
    id: "chat.search",
    title: "Search within chat",
    subtitle: "Find a message in this conversation",
    keywords: ["find", "query"],
    group: "chat",
    icon: SearchIcon,
    shortcut: "chat_search",
    when: (ctx) => ctx.hasChatPanel,
    perform: () => runtime.ui.showChatSearch(),
  },
  {
    id: "chat.jump_bottom",
    title: "Jump to bottom",
    subtitle: "Scroll to the latest message",
    keywords: ["scroll", "tail"],
    group: "chat",
    icon: ArrowDownIcon,
    when: (ctx) => ctx.hasChatPanel,
    perform: () => runtime.ui.jumpChatToBottom(),
  },
  {
    id: "chat.toggle_tool_density",
    // Stable title for fuzzy-search ranking. `getTitle` provides the
    // state-dependent display label. Keywords cover both verbs so
    // searching "expand" or "compact" both surface this row.
    title: "Toggle tool call density",
    subtitle: "Switch between compact and expanded tool rows",
    keywords: ["expand", "collapse", "compact", "rows", "tools"],
    group: "chat",
    icon: Rows3Icon,
    shortcut: "toggle_tool_density",
    when: (ctx) => ctx.hasChatPanel,
    getTitle: (): string => {
      const current = runtime.store.get(chatToolDensityAtom);
      return current === "expanded" ? "Compact tool calls" : "Expand tool calls";
    },
    getIcon: (): CommandIcon => {
      const current = runtime.store.get(chatToolDensityAtom);
      return current === "expanded" ? RowsIcon : Rows3Icon;
    },
    perform: (): void => {
      const current = runtime.store.get(chatToolDensityAtom);
      runtime.store.set(chatToolDensityAtom, current === "expanded" ? "default" : "expanded");
    },
  },
];
