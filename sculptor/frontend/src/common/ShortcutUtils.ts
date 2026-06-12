/**
 * Utility functions for handling keyboard shortcuts
 */
import { useCallback } from "react";

import { isModifierPressed } from "~/electron/utils.ts";

import { isMac } from "../electron/utils.ts";

export type ShortcutParsed = {
  meta: boolean;
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
  key: string;
};

/**
 * Parse a shortcut string like "Ctrl+N" or "Meta+P" into component parts
 */
export const parseShortcut = (shortcutString: string): ShortcutParsed => {
  const parts = shortcutString.toLowerCase().split("+");
  const result: ShortcutParsed = {
    meta: false,
    ctrl: false,
    alt: false,
    shift: false,
    key: "",
  };

  for (const part of parts) {
    const trimmed = part.trim();
    switch (trimmed) {
      case "meta":
      case "cmd":
      case "⌘":
        result.meta = true;
        break;
      case "ctrl":
      case "control":
      case "⌃":
        result.ctrl = true;
        break;
      case "alt":
      case "option":
      case "⌥":
        result.alt = true;
        break;
      case "shift":
      case "⇧":
        result.shift = true;
        break;
      default:
        // This should be the actual key
        result.key = trimmed;
        break;
    }
  }

  return result;
};

// Fallback map of shortcut key → KeyboardEvent.code, used by matchesKey only
// when no active layout map is available. Assumes a QWERTY physical layout.
const KEY_TO_CODE: Record<string, string> = {
  "[": "BracketLeft",
  "]": "BracketRight",
  "\\": "Backslash",
  "'": "Quote",
  ";": "Semicolon",
  "/": "Slash",
  ".": "Period",
  ",": "Comma",
  "`": "Backquote",
  "-": "Minus",
  "=": "Equal",
};

// event.code identifies a physical key by its QWERTY position; event.key is the
// character that key produces under the active layout. These diverge on
// non-QWERTY layouts (Dvorak, AZERTY, …). To match the character the user types,
// we resolve event.code through the active layout: navigator.keyboard.getLayoutMap
// reports each physical key's unmodified character, and we cache that map below.

type KeyboardLayoutMapLike = Iterable<readonly [string, string]> & {
  get: (code: string) => string | undefined;
};

type NavigatorKeyboard = {
  getLayoutMap?: () => Promise<KeyboardLayoutMapLike>;
  addEventListener?: (type: "layoutchange", listener: () => void) => void;
};

let activeLayoutMap: ReadonlyMap<string, string> | undefined = undefined;
let hasSubscribedToLayoutChange = false;

const getNavigatorKeyboard = (): NavigatorKeyboard | undefined => {
  if (typeof navigator === "undefined") return undefined;
  // navigator.keyboard is part of the experimental Keyboard API and is absent
  // from the DOM lib typings, so we narrow it explicitly here.
  return (navigator as Navigator & { keyboard?: NavigatorKeyboard }).keyboard;
};

const refreshLayoutMap = async (keyboard: NavigatorKeyboard): Promise<void> => {
  if (keyboard.getLayoutMap == null) return;
  try {
    activeLayoutMap = new Map(await keyboard.getLayoutMap());
  } catch {
    // The API can reject when unsupported or blocked; clear the cache so
    // matching falls back to event.key / event.code.
    activeLayoutMap = undefined;
  }
};

/**
 * Populate the active keyboard layout map and keep it current across layout
 * switches. A no-op in environments without the Keyboard Map API. Call once at
 * app startup.
 */
export const initializeKeyboardLayoutMap = (): void => {
  const keyboard = getNavigatorKeyboard();
  if (keyboard?.getLayoutMap == null) return;
  void refreshLayoutMap(keyboard);
  if (!hasSubscribedToLayoutChange && keyboard.addEventListener != null) {
    keyboard.addEventListener("layoutchange", () => {
      void refreshLayoutMap(keyboard);
    });
    hasSubscribedToLayoutChange = true;
  }
};

/**
 * Override the active layout map. Test-only seam — production populates the map
 * via initializeKeyboardLayoutMap().
 */
export const setKeyboardLayoutMapForTesting = (map: ReadonlyMap<string, string> | undefined): void => {
  activeLayoutMap = map;
};

/**
 * Decide whether the pressed key matches the shortcut's key, accounting for the
 * user's active keyboard layout.
 */
const matchesKey = (event: KeyboardEvent, shortcutKey: string): boolean => {
  const wanted = shortcutKey.toLowerCase();

  // The character the pressed physical key produces in the active layout —
  // what default bindings are written against.
  const layoutChar = activeLayoutMap?.get(event.code);
  if (layoutChar != null && layoutChar !== "" && layoutChar.toLowerCase() === wanted) return true;

  // The produced character (event.key): covers named keys absent from the layout
  // map (Enter, Tab, arrows), and custom bindings that HotkeyChip recorded from a
  // Shift/Option combo and stored as the remapped glyph.
  if (event.key.toLowerCase() === wanted) return true;

  // No layout map available: assume QWERTY and match the physical key, so
  // punctuation that Alt/Shift remap on macOS still resolves.
  if (activeLayoutMap != null) return false;
  const expectedCode = KEY_TO_CODE[shortcutKey];
  return expectedCode != null && event.code === expectedCode;
};

/**
 * Check if a KeyboardEvent matches a parsed shortcut.
 *
 * Keybinding definitions use "Meta"/"Cmd" as the platform modifier (Cmd on
 * macOS, Ctrl on Linux/Windows).  This function maps accordingly so that a
 * single definition like "Meta+W" matches Cmd+W on macOS and Ctrl+W elsewhere.
 */
export const matchesShortcut = (event: KeyboardEvent, shortcut: ShortcutParsed): boolean => {
  const isMacOS = isMac();

  let shouldRequireMeta: boolean;
  let shouldRequireCtrl: boolean;

  if (isMacOS) {
    // On macOS, meta means metaKey, ctrl means ctrlKey — no remapping.
    shouldRequireMeta = shortcut.meta;
    shouldRequireCtrl = shortcut.ctrl;
  } else {
    // On Linux/Windows, "Meta" in shortcuts maps to Ctrl.
    // Explicit "Ctrl" in shortcuts also maps to Ctrl.
    shouldRequireMeta = false;
    shouldRequireCtrl = shortcut.meta || shortcut.ctrl;
  }

  const doesModifiersMatch =
    event.metaKey === shouldRequireMeta &&
    event.ctrlKey === shouldRequireCtrl &&
    event.altKey === shortcut.alt &&
    event.shiftKey === shortcut.shift;

  if (!doesModifiersMatch) return false;

  return matchesKey(event, shortcut.key);
};

/**
 * Check whether focus is currently inside a dismissible overlay (dialog, menu,
 * popover, or select). When a Radix overlay is open it traps focus, so
 * checking the active element is a reliable way to detect this without
 * fragile DOM scanning.
 */
export const isDismissibleOverlayOpen = (): boolean => {
  const active = document.activeElement;
  if (!active || active === document.body) return false;
  return active.closest('[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]') != null;
};

/**
 * Determine whether a keybinding should be handled in the current context.
 * Checks that the event matches the shortcut string. Call sites that need
 * overlay-awareness should check isDismissibleOverlayOpen() separately.
 */
export const shouldHandleKeybinding = (event: KeyboardEvent, shortcutString: string): boolean => {
  const parsed = parseShortcut(shortcutString);
  return matchesShortcut(event, parsed);
};

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

type UseModifiedEnterOptions = {
  onConfirm: () => void;
  onInterruptAndSend?: () => void;
  sendMessageBinding: string | null;
};

export const useModifiedEnter = ({
  onConfirm,
  onInterruptAndSend,
  sendMessageBinding,
}: UseModifiedEnterOptions): ((e: KeyboardEvent) => boolean) => {
  return useCallback(
    (e: KeyboardEvent): boolean => {
      if (e.key !== "Enter" || sendMessageBinding == null) {
        return false;
      }

      // Cmd+Shift+Enter (or Ctrl+Shift+Enter) always triggers interrupt-and-send
      if (e.shiftKey && isModifierPressed(e) && onInterruptAndSend) {
        onInterruptAndSend();
        return true;
      }

      // Check if the binding matches the event
      if (shouldHandleKeybinding(e, sendMessageBinding)) {
        onConfirm();
        return true;
      }

      return false;
    },
    [onConfirm, onInterruptAndSend, sendMessageBinding],
  );
};
