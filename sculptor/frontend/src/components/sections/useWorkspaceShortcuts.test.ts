import { describe, expect, it } from "vitest";

import type { PanelId } from "./sectionTypes.ts";
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

  it("is a no-op when fewer than two panels are renderable", () => {
    const panels = panelList("agent:a", "agent:c");
    const renderable = ids("agent:a"); // only a has a definition
    expect(nextCyclablePanel(panels, renderable, "agent:a" as PanelId, 1)).toBeUndefined();
  });
});
