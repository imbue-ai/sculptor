import { describe, expect, it } from "vitest";

import type { PanelId } from "~/pages/workspace/layout/types/section.ts";

import { nextCyclablePanel } from "./useWorkspaceShortcuts.ts";

const ids = (...values: ReadonlyArray<string>): ReadonlySet<PanelId> => new Set(values as ReadonlyArray<PanelId>);
const panelList = (...values: ReadonlyArray<string>): ReadonlyArray<PanelId> => values as ReadonlyArray<PanelId>;

describe("nextCyclablePanel", () => {
  it("wraps within the renderable panels rather than stepping onto an empty slot", () => {
    const panels = panelList("agent:a", "agent:b");
    const renderable = ids("agent:a", "agent:b");
    expect(nextCyclablePanel(panels, renderable, "agent:a" as PanelId, 1)).toBe("agent:b");
    // From the last panel, next wraps back to the first — not to a def-less/empty slot.
    expect(nextCyclablePanel(panels, renderable, "agent:b" as PanelId, 1)).toBe("agent:a");
    expect(nextCyclablePanel(panels, renderable, "agent:a" as PanelId, -1)).toBe("agent:b");
  });

  it("skips open panels that have no renderable definition (agent mid-load or just deleted)", () => {
    // agent:c is open in the layout but absent from the registry, so it renders as the
    // empty-section state. Cycling from b must skip it and wrap to a, never select c.
    const panels = panelList("agent:a", "agent:b", "agent:c");
    const renderable = ids("agent:a", "agent:b");
    expect(nextCyclablePanel(panels, renderable, "agent:b" as PanelId, 1)).toBe("agent:a");
  });

  it("treats a missing or def-less active as index 0, stepping onto its neighbour", () => {
    // With no active panel (or an active id that has no renderable definition, e.g. the
    // active panel is the one mid-loading), the cycle anchors at index 0: forward lands
    // on the second renderable panel, backward wraps to the last.
    const panels = panelList("agent:a", "agent:b", "agent:c");
    const renderable = ids("agent:a", "agent:b", "agent:c");
    expect(nextCyclablePanel(panels, renderable, undefined, 1)).toBe("agent:b");
    expect(nextCyclablePanel(panels, renderable, undefined, -1)).toBe("agent:c");

    const withGhost = panelList("agent:a", "agent:b", "agent:c", "agent:ghost");
    expect(nextCyclablePanel(withGhost, renderable, "agent:ghost" as PanelId, 1)).toBe("agent:b");
    expect(nextCyclablePanel(withGhost, renderable, "agent:ghost" as PanelId, -1)).toBe("agent:c");
  });

  it("is a no-op when fewer than two panels are renderable", () => {
    const panels = panelList("agent:a", "agent:c");
    const renderable = ids("agent:a"); // only a has a definition
    expect(nextCyclablePanel(panels, renderable, "agent:a" as PanelId, 1)).toBeUndefined();
  });
});
