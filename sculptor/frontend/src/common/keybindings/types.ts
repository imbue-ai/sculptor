export type StaticKeybindingId =
  | "focus_input"
  | "chat_search"
  | "command_palette"
  | "help"
  | "home"
  | "settings"
  | "new_workspace"
  | "open_workspace"
  | "close_workspace"
  | "next_tab"
  | "previous_tab"
  | "send_message"
  | "interrupt_agent"
  | "toggle_theme"
  | "focus_mode"
  | "zen_mode"
  | "maximize_panel"
  | "toggle_left_panel"
  | "toggle_bottom_panel"
  | "toggle_right_panel"
  | "next_agent"
  | "previous_agent"
  | "new_agent"
  | "open_in_app"
  | "find_in_file"
  | "toggle_tool_density"
  | "clear_terminal"
  | "focus_pane_left"
  | "focus_pane_right"
  | "focus_pane_up"
  | "focus_pane_down"
  | "next_pane_tab"
  | "previous_pane_tab";

export type PanelKeybindingId = `panel_${string}`;

export type KeybindingId = StaticKeybindingId | PanelKeybindingId;

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

export const CATEGORY_ORDER = ["chat", "workspaces", "navigation", "general", "panels", "terminal"] as const;

export const CATEGORY_DISPLAY_NAMES: Readonly<Record<KeybindingCategory, string>> = {
  general: "General",
  workspaces: "Workspaces",
  chat: "Chat",
  navigation: "Navigation",
  panels: "Panels",
  terminal: "Terminal",
};
