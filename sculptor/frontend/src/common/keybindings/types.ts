export type StaticKeybindingId =
  | "focus_input"
  | "chat_search"
  | "command_palette"
  | "help"
  | "home"
  | "settings"
  | "new_workspace"
  | "open_workspace"
  | "delete_workspace"
  | "next_tab"
  | "previous_tab"
  | "send_message"
  | "interrupt_agent"
  | "toggle_theme"
  | "toggle_left_panel"
  | "toggle_bottom_panel"
  | "toggle_right_panel"
  | "toggle_sidebar"
  | "maximize_section"
  | "next_section"
  | "previous_section"
  | "next_panel"
  | "previous_panel"
  | "next_agent"
  | "previous_agent"
  | "new_agent"
  | "open_in_app"
  | "find_in_file"
  | "toggle_tool_density"
  | "clear_terminal";

export type KeybindingId = StaticKeybindingId;

export type KeybindingCategory = "general" | "workspaces" | "chat" | "navigation" | "panels" | "terminal";

export type KeybindingDefinition = {
  id: KeybindingId;
  name: string;
  description: string;
  category: KeybindingCategory;
  defaultBinding: string | null;
};

export type ResolvedKeybinding = KeybindingDefinition & {
  binding: string | null;
  isDefault: boolean;
};

export const CATEGORY_ORDER = [
  "chat",
  "workspaces",
  "navigation",
  "general",
  "panels",
  "terminal",
] as const satisfies ReadonlyArray<KeybindingCategory>;

export const CATEGORY_DISPLAY_NAMES: Readonly<Record<KeybindingCategory, string>> = {
  general: "General",
  workspaces: "Workspaces",
  chat: "Chat",
  navigation: "Navigation",
  panels: "Panels",
  terminal: "Terminal",
};
