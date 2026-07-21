import { describe, expect, it } from "vitest";

import { SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import { isMultiInstancePanelId } from "./registry/dynamicPanels.tsx";
import {
  isSystemDefaultLayoutId,
  isSystemLayoutId,
  SYSTEM_BROWSER_LAYOUT_ID,
  SYSTEM_CHAT_LAYOUT_ID,
  SYSTEM_DEFAULT_LAYOUT,
  SYSTEM_DEFAULT_LAYOUT_ID,
  SYSTEM_LAYOUT_SUMMARIES,
  SYSTEM_LAYOUTS,
  SYSTEM_PRESET_LAYOUTS,
  SYSTEM_REVIEW_LAYOUT_ID,
  SYSTEM_TERMINAL_LAYOUT_ID,
} from "./systemDefaultLayout.ts";

describe("SYSTEM_DEFAULT_LAYOUT", () => {
  it("captures the default static skeleton without any agent/terminal ids", () => {
    const { captured } = SYSTEM_DEFAULT_LAYOUT;

    expect(SYSTEM_DEFAULT_LAYOUT.id).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
    expect(SYSTEM_DEFAULT_LAYOUT.version).toBe(SAVED_LAYOUT_VERSION);

    // The seeded placeholder agent (center) + terminal (bottom) must be stripped.
    for (const panelId of Object.keys(captured.placement)) {
      expect(isMultiInstancePanelId(panelId)).toBe(false);
    }
    expect(captured.placement).toEqual({ files: "left", changes: "left", commits: "left" });
    expect(captured.order.left).toEqual(["files", "changes", "commits"]);
    expect(captured.activePanel.left).toBe("files");
    // No captured active tab for center — the placeholder agent there was dynamic.
    expect(captured.activePanel.center).toBeUndefined();
    expect(captured.expanded).toEqual({ left: true, right: false, bottom: false });
    expect(captured.activeSubSection).toBe("center");
    expect(captured.maximizedSection).toBeNull();
  });

  it("recognizes the System Default id", () => {
    expect(isSystemDefaultLayoutId(SYSTEM_DEFAULT_LAYOUT_ID)).toBe(true);
    expect(isSystemDefaultLayoutId("some-other-id")).toBe(false);
  });
});

describe("system preset layouts", () => {
  const PRESET_IDS = [
    SYSTEM_CHAT_LAYOUT_ID,
    SYSTEM_REVIEW_LAYOUT_ID,
    SYSTEM_TERMINAL_LAYOUT_ID,
    SYSTEM_BROWSER_LAYOUT_ID,
  ];

  it("lists System Default first, then the four presets", () => {
    expect(SYSTEM_LAYOUTS.map((layout) => layout.id)).toEqual([SYSTEM_DEFAULT_LAYOUT_ID, ...PRESET_IDS]);
    expect(SYSTEM_PRESET_LAYOUTS.map((layout) => layout.id)).toEqual(PRESET_IDS);
  });

  it("treats every built-in as a read-only system layout, but not saved ids", () => {
    for (const layout of SYSTEM_LAYOUTS) {
      expect(isSystemLayoutId(layout.id)).toBe(true);
    }
    // A preset is a system layout but NOT the System Default.
    expect(isSystemDefaultLayoutId(SYSTEM_CHAT_LAYOUT_ID)).toBe(false);
    expect(isSystemLayoutId("saved-uuid")).toBe(false);
  });

  it("gives every built-in a fixed summary, a stamped version, and tidy-on-apply", () => {
    for (const layout of SYSTEM_LAYOUTS) {
      expect(layout.version).toBe(SAVED_LAYOUT_VERSION);
      expect(SYSTEM_LAYOUT_SUMMARIES[layout.id]).toBeTruthy();
      // Built-ins tidy so switching to one produces the clean arrangement it names
      // (notably System Default → reset to the default arrangement).
      expect(layout.tidyOnApply).toBe(true);
    }
  });

  it("focuses a section without declaring agents/terminals (only static panels)", () => {
    // Chat opens nothing and collapses every side section — center only.
    const chat = SYSTEM_PRESET_LAYOUTS.find((layout) => layout.id === SYSTEM_CHAT_LAYOUT_ID)!;
    expect(chat.captured.placement).toEqual({});
    expect(chat.captured.expanded).toEqual({ left: false, right: false, bottom: false });

    // Review maximizes the center with Review All front and center.
    const review = SYSTEM_PRESET_LAYOUTS.find((layout) => layout.id === SYSTEM_REVIEW_LAYOUT_ID)!;
    expect(review.captured.placement).toEqual({ "review-all": "center" });
    expect(review.captured.maximizedSection).toBe("center");

    // Browser opens the Browser panel in an expanded right at ~half width.
    const browser = SYSTEM_PRESET_LAYOUTS.find((layout) => layout.id === SYSTEM_BROWSER_LAYOUT_ID)!;
    expect(browser.captured.placement).toEqual({ browser: "right" });
    expect(browser.captured.expanded.right).toBe(true);
    expect(browser.captured.sectionSizes.right).toBe(50);

    // Terminal opens the bottom section at ~half height (the terminal itself is the
    // workspace's own dynamic panel — presets never declare one).
    const terminal = SYSTEM_PRESET_LAYOUTS.find((layout) => layout.id === SYSTEM_TERMINAL_LAYOUT_ID)!;
    expect(terminal.captured.placement).toEqual({});
    expect(terminal.captured.expanded.bottom).toBe(true);
    expect(terminal.captured.sectionSizes.bottom).toBe(50);

    // No preset ever declares a multi-instance (agent/terminal) panel.
    for (const layout of SYSTEM_PRESET_LAYOUTS) {
      for (const panelId of Object.keys(layout.captured.placement)) {
        expect(isMultiInstancePanelId(panelId)).toBe(false);
      }
    }
  });
});
