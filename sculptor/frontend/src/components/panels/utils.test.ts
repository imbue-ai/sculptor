import { describe, expect, it } from "vitest";

import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { areArraysShallowEqual, computeToggleAction, isZoneMoveDisabled } from "~/components/panels/utils.ts";

// ── areArraysShallowEqual ────────────────────────────────────────────

describe("areArraysShallowEqual", () => {
  it("is true for the same reference", () => {
    const arr = ["a", "b"];
    expect(areArraysShallowEqual(arr, arr)).toBe(true);
  });

  it("is true for distinct arrays with equal elements", () => {
    expect(areArraysShallowEqual(["a", "b"], ["a", "b"])).toBe(true);
    expect(areArraysShallowEqual([], [])).toBe(true);
  });

  it("is false when lengths differ", () => {
    expect(areArraysShallowEqual(["a"], ["a", "b"])).toBe(false);
  });

  it("is false when elements differ or are reordered", () => {
    expect(areArraysShallowEqual(["a", "b"], ["a", "c"])).toBe(false);
    expect(areArraysShallowEqual(["a", "b"], ["b", "a"])).toBe(false);
  });
});

// ── computeToggleAction ──────────────────────────────────────────────

describe("computeToggleAction", () => {
  const defaultAssignments = {
    info: "top-left" as const,
    cost: "top-left" as const,
    terminal: "bottom" as const,
    changes: "top-right" as const,
  };

  it("should close zone when panel is active and zone is visible", () => {
    const action = computeToggleAction({
      panelId: "info",
      zoneAssignments: defaultAssignments,
      activePanelPerZone: { "top-left": "info" },
      zoneVisibility: { "top-left": true },
    });
    expect(action).toEqual({ type: "close-zone", zone: "top-left" });
  });

  it("should switch panel when different panel is active", () => {
    const action = computeToggleAction({
      panelId: "info",
      zoneAssignments: defaultAssignments,
      activePanelPerZone: { "top-left": "changes" },
      zoneVisibility: { "top-left": true },
    });
    expect(action).toEqual({ type: "switch-panel", zone: "top-left", panelId: "info" });
  });

  it("should open zone when panel is active but zone is closed", () => {
    const action = computeToggleAction({
      panelId: "info",
      zoneAssignments: defaultAssignments,
      activePanelPerZone: { "top-left": "info" },
      zoneVisibility: { "top-left": false },
    });
    expect(action).toEqual({ type: "open-zone", zone: "top-left" });
  });

  it("should open zone when panel is active and zone visibility is undefined", () => {
    const action = computeToggleAction({
      panelId: "info",
      zoneAssignments: defaultAssignments,
      activePanelPerZone: { "top-left": "info" },
      zoneVisibility: {},
    });
    expect(action).toEqual({ type: "open-zone", zone: "top-left" });
  });

  it("should switch and open when switching panels in same zone", () => {
    const assignments = {
      info: "top-left" as const,
      cost: "top-left" as const,
      terminal: "top-left" as const,
      changes: "top-right" as const,
    };
    const action = computeToggleAction({
      panelId: "terminal",
      zoneAssignments: assignments,
      activePanelPerZone: { "top-left": "info" },
      zoneVisibility: { "top-left": true },
    });
    expect(action).toEqual({ type: "switch-panel", zone: "top-left", panelId: "terminal" });
  });
});

// ── isZoneMoveDisabled ───────────────────────────────────────────────

type MakeInputsOverrides = {
  panelId?: PanelId;
  targetZone: ZoneId;
  zoneAssignments?: Record<PanelId, ZoneId>;
  disabledPanels?: ReadonlyArray<PanelId>;
};

const buildPanelsByZone = (
  zoneAssignments: Record<PanelId, ZoneId>,
  disabled: ReadonlySet<PanelId>,
): Partial<Record<ZoneId, ReadonlyArray<PanelId>>> => {
  const result: Partial<Record<ZoneId, Array<PanelId>>> = {};
  for (const [pid, zone] of Object.entries(zoneAssignments) as Array<[PanelId, ZoneId]>) {
    if (disabled.has(pid)) continue;
    (result[zone] ??= []).push(pid);
  }
  return result;
};

describe("isZoneMoveDisabled", () => {
  const makeInputs = (overrides: MakeInputsOverrides): Parameters<typeof isZoneMoveDisabled>[0] => {
    const zoneAssignments = overrides.zoneAssignments ?? {
      info: "top-left",
      cost: "top-left",
      terminal: "bottom",
      changes: "top-right",
    };
    const disabled = new Set(overrides.disabledPanels ?? []);
    return {
      panelId: overrides.panelId ?? "info",
      targetZone: overrides.targetZone,
      panelsByZone: buildPanelsByZone(zoneAssignments, disabled),
    };
  };

  it("should allow same-zone moves (reordering)", () => {
    expect(isZoneMoveDisabled(makeInputs({ targetZone: "top-left" }))).toBe(false);
  });

  it("should allow moving to a different top zone", () => {
    expect(isZoneMoveDisabled(makeInputs({ targetZone: "top-right" }))).toBe(false);
  });

  it("should allow moving to the bottom zone", () => {
    expect(isZoneMoveDisabled(makeInputs({ targetZone: "bottom" }))).toBe(false);
  });

  describe("bottom-left zone", () => {
    it("should allow when top-left retains other panels", () => {
      // info + cost are both in top-left; moving info to bottom-left leaves cost in top-left
      expect(isZoneMoveDisabled(makeInputs({ panelId: "info", targetZone: "bottom-left" }))).toBe(false);
    });

    it("should disable when top-left would be empty after the move", () => {
      // Only info is in top-left; moving it to bottom-left leaves top-left empty
      expect(
        isZoneMoveDisabled(
          makeInputs({
            panelId: "info",
            targetZone: "bottom-left",
            zoneAssignments: { info: "top-left", cost: "bottom", terminal: "bottom", changes: "top-right" },
          }),
        ),
      ).toBe(true);
    });

    it("should disable when moving from another zone and top-left is already empty", () => {
      // info is in bottom, top-left has no panels; moving info to bottom-left is invalid
      expect(
        isZoneMoveDisabled(
          makeInputs({
            panelId: "info",
            targetZone: "bottom-left",
            zoneAssignments: { info: "bottom", cost: "bottom", terminal: "bottom", changes: "top-right" },
          }),
        ),
      ).toBe(true);
    });

    it("should disable when the only sibling-top panel is disabled", () => {
      // cost is the only other panel in top-left, but it's disabled — top-left is visually empty.
      expect(
        isZoneMoveDisabled(
          makeInputs({
            panelId: "info",
            targetZone: "bottom-left",
            disabledPanels: ["cost"],
          }),
        ),
      ).toBe(true);
    });
  });

  describe("bottom-right zone", () => {
    it("should allow when top-right retains other panels", () => {
      expect(
        isZoneMoveDisabled(
          makeInputs({
            panelId: "info",
            targetZone: "bottom-right",
            zoneAssignments: { info: "top-left", cost: "top-right", terminal: "top-right", changes: "top-right" },
          }),
        ),
      ).toBe(false);
    });

    it("should disable when top-right would be empty after the move", () => {
      // changes is the only panel in top-right; moving it to bottom-right leaves top-right empty
      expect(
        isZoneMoveDisabled(
          makeInputs({
            panelId: "changes",
            targetZone: "bottom-right",
            zoneAssignments: { info: "top-left", cost: "top-left", terminal: "bottom", changes: "top-right" },
          }),
        ),
      ).toBe(true);
    });

    it("should disable when moving from another zone and top-right is already empty", () => {
      expect(
        isZoneMoveDisabled(
          makeInputs({
            panelId: "info",
            targetZone: "bottom-right",
            zoneAssignments: { info: "top-left", cost: "top-left", terminal: "bottom", changes: "bottom" },
          }),
        ),
      ).toBe(true);
    });
  });
});
