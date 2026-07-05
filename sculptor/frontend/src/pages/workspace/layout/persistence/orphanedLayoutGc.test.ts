import { beforeEach, describe, expect, it } from "vitest";

import { findOrphanedWorkspaceLayoutKeys, pruneOrphanedWorkspaceLayouts } from "./orphanedLayoutGc.ts";

describe("findOrphanedWorkspaceLayoutKeys", () => {
  it("selects only layout keys whose workspace id is not live", () => {
    const stored = ["sculptor-layout-ws-ws-live", "sculptor-layout-ws-ws-gone", "sculptor-layout-ws-ws-also-gone"];
    const orphans = findOrphanedWorkspaceLayoutKeys(stored, new Set(["ws-live"]));
    expect(orphans).toEqual(["sculptor-layout-ws-ws-gone", "sculptor-layout-ws-ws-also-gone"]);
  });

  it("never selects non-layout keys, even lookalikes", () => {
    const stored = [
      "sculptor-layout-global",
      "sculptor-tabs",
      "diffPanel-state-ws-gone",
      // Lookalike without the trailing dash of the real prefix.
      "sculptor-layout-ws",
    ];
    expect(findOrphanedWorkspaceLayoutKeys(stored, new Set())).toEqual([]);
  });

  it("selects nothing when every stored layout has a live workspace", () => {
    const stored = ["sculptor-layout-ws-a", "sculptor-layout-ws-b"];
    expect(findOrphanedWorkspaceLayoutKeys(stored, new Set(["a", "b"]))).toEqual([]);
  });
});

describe("pruneOrphanedWorkspaceLayouts", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("removes orphaned layout keys and leaves everything else alone", () => {
    localStorage.setItem("sculptor-layout-ws-ws-live", "{}");
    localStorage.setItem("sculptor-layout-ws-ws-gone", "{}");
    localStorage.setItem("sculptor-layout-global", "{}");
    localStorage.setItem("diffPanel-state-ws-gone", "{}");

    pruneOrphanedWorkspaceLayouts(new Set(["ws-live"]));

    expect(localStorage.getItem("sculptor-layout-ws-ws-live")).toBe("{}");
    expect(localStorage.getItem("sculptor-layout-ws-ws-gone")).toBeNull();
    expect(localStorage.getItem("sculptor-layout-global")).toBe("{}");
    expect(localStorage.getItem("diffPanel-state-ws-gone")).toBe("{}");
  });

  it("is a no-op with an empty store", () => {
    expect(() => pruneOrphanedWorkspaceLayouts(new Set(["ws-live"]))).not.toThrow();
  });
});
