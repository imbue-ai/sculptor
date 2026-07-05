import { isMac } from "~/electron/utils.ts";

/**
 * Convert shortcut modifiers to platform-specific symbols
 */
export const formatShortcutForDisplay = (shortcut: string | undefined): string => {
  if (!shortcut) {
    return "";
  }

  const isMacOS = isMac();
  const separator = isMacOS ? "" : "+";

  return shortcut
    .split("+")
    .map((part) => {
      const trimmed = part.trim().toLowerCase();
      switch (trimmed) {
        case "cmd":
        case "meta":
          return isMacOS ? "⌘" : "Ctrl";
        case "ctrl":
        case "control":
          return isMacOS ? "⌃" : "Ctrl";
        case "alt":
        case "option":
          return isMacOS ? "⌥" : "Alt";
        case "shift":
          return isMacOS ? "⇧" : "Shift";
        case "enter":
          return "↵";
        case "escape":
          return "Esc";
        case "arrowleft":
          return "←";
        case "arrowright":
          return "→";
        case "arrowup":
          return "↑";
        case "arrowdown":
          return "↓";
        default:
          return part.trim().toUpperCase();
      }
    })
    .join(separator);
};
