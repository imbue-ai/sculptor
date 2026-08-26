import { describe, expect, it } from "vitest";

import type { CapturedLayout } from "~/components/sections/persistence/types.ts";
import { DEFAULT_SECTION_SIZES } from "~/components/sections/persistence/types.ts";

import { describeLayout } from "./layoutSummary.ts";

function captured(overrides: Partial<CapturedLayout>): CapturedLayout {
  return {
    placement: {},
    order: {},
    activePanel: {},
    expanded: {},
    splits: {},
    sectionSizes: DEFAULT_SECTION_SIZES,
    maximizedSection: null,
    activeSubSection: null,
    ...overrides,
  };
}

// Title-case the id for a readable stub name (files → Files).
const nameOf = (id: string): string => id.charAt(0).toUpperCase() + id.slice(1);

describe("describeLayout", () => {
  it("groups static panels by section, in section order, with a proper list join", () => {
    const summary = describeLayout(
      captured({
        placement: { changes: "left", commits: "left", browser: "right" },
        order: { left: ["changes", "commits"], right: ["browser"] },
      }),
      nameOf,
    );
    expect(summary).toBe("Changes & Commits left · Browser right");
  });

  it("joins three or more panels with commas and an ampersand", () => {
    const summary = describeLayout(
      captured({
        placement: { files: "left", changes: "left", commits: "left" },
        order: { left: ["files", "changes", "commits"] },
      }),
      nameOf,
    );
    expect(summary).toBe("Files, Changes & Commits left");
  });

  it("says 'Just the agent, full width' when there are no static panels", () => {
    expect(describeLayout(captured({}), nameOf)).toBe("Just the agent, full width");
  });

  it("uses 'below' for the bottom section", () => {
    const summary = describeLayout(captured({ placement: { notes: "bottom" }, order: { bottom: ["notes"] } }), nameOf);
    expect(summary).toBe("Notes below");
  });
});
