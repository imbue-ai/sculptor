import { describe, expect, it } from "vitest";

import { inSentence, sectionDestinations } from "./destinations.ts";
import type { SectionSplit } from "./sectionLayoutAtoms.ts";
import type { ZoneId } from "./types.ts";

describe("sectionDestinations", () => {
  it("lists each section once, in order, when nothing is split", () => {
    expect(sectionDestinations({})).toEqual([
      { zone: "top-left", label: "Left" },
      { zone: "center", label: "Center" },
      { zone: "top-right", label: "Right" },
      { zone: "bottom", label: "Bottom" },
    ]);
  });

  it("expands a horizontally split section into natural Top/Bottom halves", () => {
    const split: Partial<Record<ZoneId, SectionSplit>> = { "top-right": { axis: "horizontal", ratio: 0.5 } };
    const dests = sectionDestinations(split);
    expect(dests).toContainEqual({ zone: "top-right", label: "Top right" });
    expect(dests).toContainEqual({ zone: "top-right:split", label: "Bottom right" });
    // Unsplit sections are unaffected — no phantom halves.
    expect(dests).toContainEqual({ zone: "top-left", label: "Left" });
    expect(dests).toContainEqual({ zone: "bottom", label: "Bottom" });
  });

  it("expands a vertically split section into left/right halves", () => {
    const split: Partial<Record<ZoneId, SectionSplit>> = { bottom: { axis: "vertical", ratio: 0.5 } };
    const dests = sectionDestinations(split);
    expect(dests).toContainEqual({ zone: "bottom", label: "Bottom left" });
    expect(dests).toContainEqual({ zone: "bottom:split", label: "Bottom right" });
  });
});

describe("inSentence", () => {
  it("lowercases a label for mid-sentence use", () => {
    expect(inSentence("Top right")).toBe("top right");
    expect(inSentence("Right")).toBe("right");
  });
});
