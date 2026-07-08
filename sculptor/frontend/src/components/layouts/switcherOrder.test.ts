import { describe, expect, it } from "vitest";

import type { SavedLayout } from "~/components/sections/persistence/types.ts";
import { SAVED_LAYOUT_VERSION } from "~/components/sections/persistence/types.ts";
import { SYSTEM_DEFAULT_LAYOUT } from "~/components/sections/systemDefaultLayout.ts";

import { initialHighlightIndex, orderLayoutsByMru } from "./switcherOrder.ts";

function layout(id: string): SavedLayout {
  return { id, name: id, version: SAVED_LAYOUT_VERSION, captured: SYSTEM_DEFAULT_LAYOUT.captured };
}

const candidates = [layout("system-default"), layout("focused"), layout("review"), layout("debugging")];

describe("orderLayoutsByMru", () => {
  it("orders applied layouts by recency, then never-applied ones in input order", () => {
    const ordered = orderLayoutsByMru(candidates, ["review", "focused"]);
    expect(ordered.map((l) => l.id)).toEqual(["review", "focused", "system-default", "debugging"]);
  });

  it("keeps the input order when nothing has been applied", () => {
    const ordered = orderLayoutsByMru(candidates, []);
    expect(ordered.map((l) => l.id)).toEqual(["system-default", "focused", "review", "debugging"]);
  });
});

describe("initialHighlightIndex", () => {
  it("lands on the first row that is not the current layout", () => {
    const ordered = [layout("review"), layout("focused"), layout("system-default")];
    // review is current → highlight the next one (focused, the previous layout).
    expect(initialHighlightIndex(ordered, "review")).toBe(1);
  });

  it("falls back to the first row when there is no current or it's the only one", () => {
    expect(initialHighlightIndex([layout("only")], "only")).toBe(0);
    expect(initialHighlightIndex([layout("a"), layout("b")], undefined)).toBe(0);
    expect(initialHighlightIndex([], "x")).toBe(0);
  });
});
