import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { parseShortcut, setKeyboardLayoutMapForTesting, shouldHandleKeybinding } from "./matching.ts";

// Helper to create a fake KeyboardEvent-like object for matchesShortcut.
// jsdom's KeyboardEvent constructor doesn't support metaKey/ctrlKey in the
// init dict reliably, so we build a plain object instead.
const fakeKeyEvent = (overrides: {
  key: string;
  code?: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
}): KeyboardEvent =>
  ({
    key: overrides.key,
    code: overrides.code ?? "",
    metaKey: overrides.metaKey ?? false,
    ctrlKey: overrides.ctrlKey ?? false,
    altKey: overrides.altKey ?? false,
    shiftKey: overrides.shiftKey ?? false,
  }) as unknown as KeyboardEvent;

describe("parseShortcut", () => {
  it("parses Cmd modifier", () => {
    const parsed = parseShortcut("Cmd+K");
    expect(parsed).toEqual({ meta: true, ctrl: false, alt: false, shift: false, key: "k" });
  });

  it("parses Meta modifier", () => {
    const parsed = parseShortcut("Meta+I");
    expect(parsed).toEqual({ meta: true, ctrl: false, alt: false, shift: false, key: "i" });
  });

  it("parses Ctrl modifier", () => {
    const parsed = parseShortcut("Ctrl+T");
    expect(parsed).toEqual({ meta: false, ctrl: true, alt: false, shift: false, key: "t" });
  });

  it("parses Ctrl+Shift combination", () => {
    const parsed = parseShortcut("Ctrl+Shift+Tab");
    expect(parsed).toEqual({ meta: false, ctrl: true, alt: false, shift: true, key: "tab" });
  });

  it("parses Alt modifier", () => {
    const parsed = parseShortcut("Alt+X");
    expect(parsed).toEqual({ meta: false, ctrl: false, alt: true, shift: false, key: "x" });
  });

  it("parses macOS symbol modifiers", () => {
    expect(parseShortcut("⌘+K")).toEqual({ meta: true, ctrl: false, alt: false, shift: false, key: "k" });
    expect(parseShortcut("⌃+K")).toEqual({ meta: false, ctrl: true, alt: false, shift: false, key: "k" });
    expect(parseShortcut("⌥+K")).toEqual({ meta: false, ctrl: false, alt: true, shift: false, key: "k" });
    expect(parseShortcut("⇧+K")).toEqual({ meta: false, ctrl: false, alt: false, shift: true, key: "k" });
  });
});

describe("shouldHandleKeybinding", () => {
  const savedSculptor = window.sculptor;

  afterEach(() => {
    if (savedSculptor === undefined) {
      delete (window as unknown as Record<string, unknown>).sculptor;
    } else {
      window.sculptor = savedSculptor;
    }
  });

  describe("on macOS", () => {
    beforeEach(() => {
      window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;
    });

    it("matches Cmd+K with metaKey pressed", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "k", metaKey: true }), "Cmd+K")).toBe(true);
    });

    it("does not match Cmd+K with ctrlKey on macOS", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "k", ctrlKey: true }), "Cmd+K")).toBe(false);
    });

    it("does not match when extra modifiers are pressed", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "k", metaKey: true, shiftKey: true }), "Cmd+K")).toBe(false);
    });
  });

  describe("on Linux", () => {
    beforeEach(() => {
      window.sculptor = { platform: "linux" } as unknown as typeof window.sculptor;
    });

    it("matches Cmd+K (Meta shortcut) with ctrlKey on Linux", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "k", ctrlKey: true }), "Cmd+K")).toBe(true);
    });

    it("does not match Cmd+K with metaKey on Linux", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "k", metaKey: true }), "Cmd+K")).toBe(false);
    });

    it("matches Meta+W with ctrlKey on Linux", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "w", ctrlKey: true }), "Meta+W")).toBe(true);
    });
  });

  it("matches Ctrl+Shift+Tab", () => {
    // Ctrl+Shift is explicit ctrl, works the same on all platforms
    expect(shouldHandleKeybinding(fakeKeyEvent({ key: "Tab", ctrlKey: true, shiftKey: true }), "Ctrl+Shift+Tab")).toBe(
      true,
    );
  });

  it("does not match wrong key", () => {
    window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;
    expect(shouldHandleKeybinding(fakeKeyEvent({ key: "j", metaKey: true }), "Cmd+K")).toBe(false);
  });

  it("is case-insensitive for key matching", () => {
    window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;
    expect(shouldHandleKeybinding(fakeKeyEvent({ key: "K", metaKey: true }), "Cmd+k")).toBe(true);
  });

  describe("Alt+bracket shortcuts on macOS", () => {
    beforeEach(() => {
      window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;
    });

    it("matches Meta+Alt+[ via event.code when Alt remaps the key", () => {
      // On macOS, Opt+[ produces "“" instead of "[", so event.key is wrong.
      // The fix uses event.code (BracketLeft) as a fallback.
      expect(
        shouldHandleKeybinding(
          fakeKeyEvent({ key: "“", code: "BracketLeft", metaKey: true, altKey: true }),
          "Meta+Alt+[",
        ),
      ).toBe(true);
    });

    it("matches Meta+Alt+] via event.code when Alt remaps the key", () => {
      expect(
        shouldHandleKeybinding(
          fakeKeyEvent({ key: "‘", code: "BracketRight", metaKey: true, altKey: true }),
          "Meta+Alt+]",
        ),
      ).toBe(true);
    });

    it("does not match Meta+Alt+[ when wrong physical key is pressed", () => {
      expect(
        shouldHandleKeybinding(
          fakeKeyEvent({ key: "‘", code: "BracketRight", metaKey: true, altKey: true }),
          "Meta+Alt+[",
        ),
      ).toBe(false);
    });
  });

  describe("Shift+bracket shortcuts", () => {
    beforeEach(() => {
      window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;
    });

    it("matches Meta+Shift+[ via event.code when Shift remaps [ to {", () => {
      expect(
        shouldHandleKeybinding(
          fakeKeyEvent({ key: "{", code: "BracketLeft", metaKey: true, shiftKey: true }),
          "Meta+Shift+[",
        ),
      ).toBe(true);
    });

    it("matches Meta+Shift+] via event.code when Shift remaps ] to }", () => {
      expect(
        shouldHandleKeybinding(
          fakeKeyEvent({ key: "}", code: "BracketRight", metaKey: true, shiftKey: true }),
          "Meta+Shift+]",
        ),
      ).toBe(true);
    });
  });

  describe("Dvorak layout (event.code differs from the produced character)", () => {
    // On Dvorak the physical key QWERTY calls `Slash` produces "z", `Comma`
    // produces "w", `Period` produces "v", and "/" lives on `BracketLeft`.
    const DVORAK_LAYOUT: ReadonlyMap<string, string> = new Map([
      ["Slash", "z"],
      ["Comma", "w"],
      ["Period", "v"],
      ["BracketLeft", "/"],
      ["BracketRight", "="],
      ["KeyV", "k"],
      ["KeyZ", ";"],
    ]);

    beforeEach(() => {
      window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;
      setKeyboardLayoutMapForTesting(DVORAK_LAYOUT);
    });

    afterEach(() => {
      setKeyboardLayoutMapForTesting(undefined);
    });

    it("does not trigger the Meta+/ binding when Cmd+Z is pressed", () => {
      // The reported bug: Cmd+Z (physical Slash, which types "z" on Dvorak) also
      // opened the Meta+/ help dialog because matching fell back to event.code.
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "z", code: "Slash", metaKey: true }), "Meta+/")).toBe(false);
    });

    it("triggers a Meta+Z binding when Cmd+Z is pressed", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "z", code: "Slash", metaKey: true }), "Meta+Z")).toBe(true);
    });

    it("triggers the Meta+/ binding when the Dvorak slash key (BracketLeft) is pressed", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "/", code: "BracketLeft", metaKey: true }), "Meta+/")).toBe(
        true,
      );
    });

    it("does not trigger the Meta+, settings binding when Cmd+W is pressed", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "w", code: "Comma", metaKey: true }), "Meta+,")).toBe(false);
    });

    it("still triggers the Meta+W binding when Cmd+W is pressed", () => {
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "w", code: "Comma", metaKey: true }), "Meta+W")).toBe(true);
    });

    it("matches a letter shortcut by produced character, not physical position", () => {
      // The Dvorak "k" sits on the physical `KeyV` key.
      expect(shouldHandleKeybinding(fakeKeyEvent({ key: "k", code: "KeyV", metaKey: true }), "Meta+K")).toBe(true);
    });
  });

  describe("user-recorded modifier-remapped bindings (layout map active)", () => {
    // HotkeyChip records custom bindings from event.key, so a Shift/Option combo
    // is stored as the remapped glyph (Shift+] → "}", Option+P → "π") while the
    // layout map reports each key's base glyph. The matcher must accept both.
    const QWERTY_LAYOUT: ReadonlyMap<string, string> = new Map([
      ["BracketLeft", "["],
      ["BracketRight", "]"],
      ["KeyP", "p"],
    ]);

    beforeEach(() => {
      window.sculptor = { platform: "darwin" } as unknown as typeof window.sculptor;
      setKeyboardLayoutMapForTesting(QWERTY_LAYOUT);
    });

    afterEach(() => {
      setKeyboardLayoutMapForTesting(undefined);
    });

    it("matches a Shift+punctuation binding stored as its remapped glyph", () => {
      // Recorded by pressing Cmd+Shift+] (event.key "}"), stored as "Meta+Shift+}".
      expect(
        shouldHandleKeybinding(
          fakeKeyEvent({ key: "}", code: "BracketRight", metaKey: true, shiftKey: true }),
          "Meta+Shift+}",
        ),
      ).toBe(true);
    });

    it("matches an Option+key binding stored as its remapped glyph", () => {
      // Recorded by pressing Cmd+Option+P (event.key "π"), stored as "Meta+Alt+π".
      expect(
        shouldHandleKeybinding(fakeKeyEvent({ key: "π", code: "KeyP", metaKey: true, altKey: true }), "Meta+Alt+π"),
      ).toBe(true);
    });

    it("still matches a base-glyph default such as Meta+Shift+[", () => {
      expect(
        shouldHandleKeybinding(
          fakeKeyEvent({ key: "{", code: "BracketLeft", metaKey: true, shiftKey: true }),
          "Meta+Shift+[",
        ),
      ).toBe(true);
    });
  });
});
