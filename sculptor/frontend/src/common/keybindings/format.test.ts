import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { formatShortcutForDisplay } from "./format.ts";

describe("formatShortcutForDisplay", () => {
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

    it("converts Cmd to ⌘ symbol without separator", () => {
      expect(formatShortcutForDisplay("Cmd+K")).toBe("⌘K");
    });

    it("converts Meta to ⌘ symbol", () => {
      expect(formatShortcutForDisplay("Meta+I")).toBe("⌘I");
    });

    it("converts Ctrl to ⌃ symbol", () => {
      expect(formatShortcutForDisplay("Ctrl+Tab")).toBe("⌃TAB");
    });

    it("converts Shift to ⇧ symbol", () => {
      expect(formatShortcutForDisplay("Ctrl+Shift+Tab")).toBe("⌃⇧TAB");
    });

    it("converts Alt to ⌥ symbol", () => {
      expect(formatShortcutForDisplay("Alt+X")).toBe("⌥X");
    });

    it("converts ArrowLeft to ← symbol", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowLeft")).toBe("⌘⇧←");
    });

    it("converts ArrowRight to → symbol", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowRight")).toBe("⌘⇧→");
    });

    it("converts ArrowUp to ↑ symbol", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowUp")).toBe("⌘⇧↑");
    });

    it("converts ArrowDown to ↓ symbol", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowDown")).toBe("⌘⇧↓");
    });

    it("converts Escape to Esc (not ESCAPE)", () => {
      expect(formatShortcutForDisplay("Escape")).toBe("Esc");
    });
  });

  describe("on Linux", () => {
    beforeEach(() => {
      window.sculptor = { platform: "linux" } as unknown as typeof window.sculptor;
    });

    it("converts Cmd to Ctrl with + separator", () => {
      expect(formatShortcutForDisplay("Cmd+K")).toBe("Ctrl+K");
    });

    it("converts Meta to Ctrl with + separator", () => {
      expect(formatShortcutForDisplay("Meta+I")).toBe("Ctrl+I");
    });

    it("keeps Ctrl as Ctrl", () => {
      expect(formatShortcutForDisplay("Ctrl+Tab")).toBe("Ctrl+TAB");
    });

    it("converts Shift to Shift with + separator", () => {
      expect(formatShortcutForDisplay("Ctrl+Shift+Tab")).toBe("Ctrl+Shift+TAB");
    });

    it("converts Alt to Alt", () => {
      expect(formatShortcutForDisplay("Alt+X")).toBe("Alt+X");
    });

    it("converts ArrowLeft to ← symbol on Linux", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowLeft")).toBe("Ctrl+Shift+←");
    });

    it("converts ArrowRight to → symbol on Linux", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowRight")).toBe("Ctrl+Shift+→");
    });

    it("converts ArrowUp to ↑ symbol on Linux", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowUp")).toBe("Ctrl+Shift+↑");
    });

    it("converts ArrowDown to ↓ symbol on Linux", () => {
      expect(formatShortcutForDisplay("Meta+Shift+ArrowDown")).toBe("Ctrl+Shift+↓");
    });
  });

  it("returns empty string for undefined input", () => {
    expect(formatShortcutForDisplay(undefined)).toBe("");
  });
});
