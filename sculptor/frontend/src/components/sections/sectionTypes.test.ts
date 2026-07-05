import { describe, expect, it } from "vitest";

import {
  allowedSplitAxesForSection,
  canSplitAxis,
  isSecondary,
  isSectionId,
  primaryOf,
  SECTION_IDS,
  type SectionId,
  splitDirectionLabel,
  splitDirectionOptionsForSection,
  toSecondary,
  toSection,
} from "./sectionTypes.ts";

describe("sectionTypes keyspace helpers", () => {
  it("round-trips toSecondary/toSection for every section", () => {
    for (const section of SECTION_IDS) {
      expect(toSection(toSecondary(section))).toBe(section);
    }
  });

  it("returns the section id unchanged when toSection is given a primary id", () => {
    for (const section of SECTION_IDS) {
      expect(toSection(section)).toBe(section);
    }
  });

  it("isSecondary is true only for :secondary ids", () => {
    for (const section of SECTION_IDS) {
      expect(isSecondary(section)).toBe(false);
      expect(isSecondary(toSecondary(section))).toBe(true);
    }
  });

  it("primaryOf returns the section id (no :primary suffix)", () => {
    for (const section of SECTION_IDS) {
      expect(primaryOf(section)).toBe(section);
    }
  });

  it("toSecondary uses the :secondary suffix", () => {
    expect(toSecondary("left")).toBe("left:secondary");
    expect(toSecondary("center")).toBe("center:secondary");
  });
});

describe("isSectionId", () => {
  it("accepts the four section ids", () => {
    for (const section of SECTION_IDS) {
      expect(isSectionId(section)).toBe(true);
    }
  });

  it("rejects sub-section ids and arbitrary values", () => {
    expect(isSectionId("left:secondary")).toBe(false);
    expect(isSectionId("bottom-left")).toBe(false);
    expect(isSectionId("")).toBe(false);
    expect(isSectionId(undefined)).toBe(false);
    expect(isSectionId(42)).toBe(false);
  });
});

describe("split axis rules", () => {
  it("left/right allow only a horizontal (stacked) split", () => {
    for (const section of ["left", "right"] as const) {
      expect(allowedSplitAxesForSection(section)).toEqual(["horizontal"]);
      expect(canSplitAxis(section, "horizontal")).toBe(true);
      expect(canSplitAxis(section, "vertical")).toBe(false);
    }
  });

  it("bottom allows only a vertical (side-by-side) split", () => {
    expect(allowedSplitAxesForSection("bottom")).toEqual(["vertical"]);
    expect(canSplitAxis("bottom", "vertical")).toBe(true);
    expect(canSplitAxis("bottom", "horizontal")).toBe(false);
  });

  it("center allows either direction", () => {
    expect(allowedSplitAxesForSection("center")).toEqual(["horizontal", "vertical"]);
    expect(canSplitAxis("center", "horizontal")).toBe(true);
    expect(canSplitAxis("center", "vertical")).toBe(true);
  });

  it("covers every section id", () => {
    for (const section of SECTION_IDS as ReadonlyArray<SectionId>) {
      expect(allowedSplitAxesForSection(section).length).toBeGreaterThan(0);
    }
  });
});

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
