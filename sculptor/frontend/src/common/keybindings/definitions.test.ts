import { describe, expect, it } from "vitest";

import { KEYBINDING_DEFINITIONS } from "./definitions.ts";

/**
 * Blocklisted shortcuts that must never be used as default keybindings.
 *
 * This list is the source of truth enforced by the test below.
 *
 * To allow a blocked shortcut, remove it from this array. The MR diff
 * makes the decision visible and reviewable.
 *
 * Shortcut format uses the same notation as definitions.ts:
 *   "Meta+K", "Meta+Shift+ArrowLeft", "Ctrl+A", "Alt+ArrowLeft", etc.
 * Comparison is case-insensitive.
 */
const BLOCKLISTED_SHORTCUTS: Array<string> = [
  // OS fundamentals
  "Meta+C",
  "Meta+V",
  "Meta+X",
  "Meta+Z",
  "Meta+Shift+Z",
  "Meta+A",
  "Meta+Q",
  "Meta+H",
  "Meta+M",
  "Meta+Tab",
  "Meta+Space",
  "Meta+R",
  "Meta+Shift+R",
  "Meta+Shift+3",
  "Meta+Shift+4",
  "Meta+Shift+5",
  "Meta+`",
  "Meta+Ctrl+F",
  "Meta+Ctrl+Q",
  "Meta+Shift+Q",

  "Meta+0",
  "Meta++",
  "Meta+-",

  // Cursor movement
  "Meta+ArrowLeft",
  "Meta+ArrowRight",
  "Meta+ArrowUp",
  "Meta+ArrowDown",
  "Alt+ArrowLeft",
  "Alt+ArrowRight",
  "Alt+ArrowUp",
  "Alt+ArrowDown",

  // Text selection
  "Meta+Shift+ArrowLeft",
  "Meta+Shift+ArrowRight",
  "Meta+Shift+ArrowUp",
  "Meta+Shift+ArrowDown",
  "Alt+Shift+ArrowLeft",
  "Alt+Shift+ArrowRight",
  "Alt+Shift+ArrowUp",
  "Alt+Shift+ArrowDown",
  "Shift+ArrowLeft",
  "Shift+ArrowRight",
  "Shift+ArrowUp",
  "Shift+ArrowDown",

  // Deletion
  "Meta+Backspace",
  "Alt+Backspace",
  "Alt+Delete",

  // macOS Emacs-style
  "Ctrl+A",
  "Ctrl+E",
  "Ctrl+F",
  "Ctrl+B",
  "Ctrl+N",
  "Ctrl+P",
  "Ctrl+D",
  "Ctrl+H",
  "Ctrl+K",
  "Ctrl+T",
  "Ctrl+O",

  // TipTap / ProseMirror StarterKit defaults — consumed inside the chat editor.
  // Any shortcut here will be eaten by the editor before global handlers see it.
  // Exceptions intentionally kept off this list (handled at the input layer):
  //   Meta+Enter → send_message (hardBreak overridden)
  //   Meta+I     → focus_input (italic — only fires from outside the editor)
  "Meta+B",
  "Meta+U",
  "Meta+E",
  "Meta+Shift+S",
  "Meta+Shift+7",
  "Meta+Shift+8",
  "Meta+Shift+B",
  "Meta+Alt+0",
  "Meta+Alt+1",
  "Meta+Alt+2",
  "Meta+Alt+3",
  "Meta+Alt+4",
  "Meta+Alt+5",
  "Meta+Alt+6",
  "Meta+Alt+C",
];

const blocklist = new Set(BLOCKLISTED_SHORTCUTS.map((s) => s.toLowerCase()));

describe("KEYBINDING_DEFINITIONS", () => {
  it("has no duplicate default bindings", () => {
    const bindings = KEYBINDING_DEFINITIONS.map((d) => d.defaultBinding);
    const uniqueBindings = new Set(bindings);
    expect(uniqueBindings.size).toBe(bindings.length);
  });

  it("has no duplicate ids", () => {
    const ids = KEYBINDING_DEFINITIONS.map((d) => d.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });

  it("every definition has a non-empty name and description", () => {
    const bad = KEYBINDING_DEFINITIONS.filter(
      (d) => !d.name || d.name.trim().length === 0 || !d.description || d.description.trim().length === 0,
    );
    expect(bad).toEqual([]);
  });

  it("blocklist includes Meta+Shift+B (TipTap blockquote)", () => {
    // Regression guard: removing this from the blocklist lets TipTap's
    // blockquote shortcut collide with any chat shortcut bound to the same
    // combo.  See commit d8c77629.
    expect(BLOCKLISTED_SHORTCUTS).toContain("Meta+Shift+B");
  });

  it("has no default bindings that conflict with the blocklist", () => {
    const violations = KEYBINDING_DEFINITIONS.filter(
      (d) => d.defaultBinding != null && blocklist.has(d.defaultBinding.toLowerCase()),
    );

    if (violations.length > 0) {
      const details = violations.map((d) => `  "${d.id}" uses blocklisted shortcut "${d.defaultBinding}"`).join("\n");
      expect.fail(
        `Default keybindings conflict with OS/editor shortcuts:\n${details}\n\n` +
          `To fix: change the default in definitions.ts, or remove the shortcut ` +
          `from the BLOCKLISTED_SHORTCUTS array in definitions.test.ts.`,
      );
    }
  });
});
