import { describe, expect, it } from "vitest";

import { splitDirectionLabel, splitDirectionOptionsForSection } from "./splitDirection.ts";

describe("splitDirectionLabel", () => {
  it("labels a horizontal divider 'bottom' (secondary stacked below)", () => {
    expect(splitDirectionLabel("horizontal")).toBe("bottom");
  });

  it("labels a vertical divider 'right' (secondary side-by-side)", () => {
    expect(splitDirectionLabel("vertical")).toBe("right");
  });
});

describe("splitDirectionOptionsForSection", () => {
  it("offers only a bottom split for the left and right sections", () => {
    for (const section of ["left", "right"] as const) {
      expect(splitDirectionOptionsForSection(section)).toEqual([{ axis: "horizontal", label: "bottom" }]);
    }
  });

  it("offers only a right split for the bottom section", () => {
    expect(splitDirectionOptionsForSection("bottom")).toEqual([{ axis: "vertical", label: "right" }]);
  });

  it("offers both directions for the center section", () => {
    expect(splitDirectionOptionsForSection("center")).toEqual([
      { axis: "horizontal", label: "bottom" },
      { axis: "vertical", label: "right" },
    ]);
  });
});
