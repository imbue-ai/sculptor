import { describe, expect, it } from "vitest";

import { SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import { isMultiInstancePanelId } from "./registry/dynamicPanels.tsx";
import { isSystemDefaultLayoutId, SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID } from "./systemDefaultLayout.ts";

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
