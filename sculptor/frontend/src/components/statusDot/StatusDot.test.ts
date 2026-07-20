import { describe, expect, it } from "vitest";

import { DOT_SCALE, dotDiameter, pulseTiming, resolveWorkspaceDotStatuses } from "./statusDotHelpers";
import { EMPTY_WORKSPACE_DOT_STATUS, type WorkspaceDotStatus } from "./statusUtils";

const status = (overrides: Partial<WorkspaceDotStatus>): WorkspaceDotStatus => ({
  ...EMPTY_WORKSPACE_DOT_STATUS,
  ...overrides,
});

describe("resolveWorkspaceDotStatuses", () => {
  it("pairs a partial error with the best summary of the remaining agents", () => {
    // Secondary dot priority: running > waiting > unread > read.
    expect(
      resolveWorkspaceDotStatuses(status({ hasError: true, hasRunning: true, hasWaiting: true, hasUnread: true })),
    ).toEqual(["error", "running"]);
    expect(resolveWorkspaceDotStatuses(status({ hasError: true, hasWaiting: true, hasUnread: true }))).toEqual([
      "error",
      "waiting",
    ]);
    expect(resolveWorkspaceDotStatuses(status({ hasError: true, hasUnread: true }))).toEqual(["error", "unread"]);
    expect(resolveWorkspaceDotStatuses(status({ hasError: true }))).toEqual(["error", "read"]);
  });

  it("collapses an all-error workspace to a single error dot", () => {
    // No secondary dot: there is no non-errored remainder to summarise, even if
    // the errored agents also carry unread output.
    expect(resolveWorkspaceDotStatuses(status({ hasError: true, isAllError: true, hasUnread: true }))).toEqual([
      "error",
    ]);
  });

  it("prefers waiting over running when there is no error", () => {
    expect(resolveWorkspaceDotStatuses(status({ hasWaiting: true, hasRunning: true, hasUnread: true }))).toEqual([
      "waiting",
    ]);
  });

  it("prefers running over unread/read when nothing is waiting", () => {
    expect(resolveWorkspaceDotStatuses(status({ hasRunning: true, hasUnread: true }))).toEqual(["running"]);
  });

  it("falls through to unread, then read", () => {
    expect(resolveWorkspaceDotStatuses(status({ hasUnread: true }))).toEqual(["unread"]);
    expect(resolveWorkspaceDotStatuses(EMPTY_WORKSPACE_DOT_STATUS)).toEqual(["read"]);
  });
});

// pulseTiming emits CSS strings ("2.13s" / "-0.45s"); parse them back to
// numbers for the arithmetic assertions.
const seconds = (value: unknown): number => Number.parseFloat(String(value));

describe("pulseTiming", () => {
  it("is deterministic: the same seed always yields the same timing", () => {
    expect(pulseTiming("agent-r1")).toEqual(pulseTiming("agent-r1"));
  });

  it("keeps the loop duration within the documented 1.70s-2.29s band", () => {
    for (const seed of ["a", "agent-r1", ":r0:", "some-much-longer-instance-id"]) {
      const duration = seconds(pulseTiming(seed).halo.animationDuration);
      expect(duration).toBeGreaterThanOrEqual(1.7);
      expect(duration).toBeLessThanOrEqual(2.29);
    }
  });

  it("starts both halos mid-cycle via non-positive delays", () => {
    const { halo, haloTrailing } = pulseTiming("agent-r1");
    expect(seconds(halo.animationDelay)).toBeLessThanOrEqual(0);
    expect(seconds(haloTrailing.animationDelay)).toBeLessThanOrEqual(0);
  });

  it("trails the second halo by half a loop so the pings alternate", () => {
    for (const seed of ["a", "agent-r1", ":r0:"]) {
      const { halo, haloTrailing } = pulseTiming(seed);
      // Both halos share one loop duration; only their phase differs.
      expect(haloTrailing.animationDuration).toBe(halo.animationDuration);
      const duration = seconds(halo.animationDuration);
      const offset = seconds(halo.animationDelay) - seconds(haloTrailing.animationDelay);
      // Each delay is rounded to 2dp independently, so allow 0.01s of slack.
      expect(Math.abs(offset - duration / 2)).toBeLessThanOrEqual(0.011);
    }
  });
});

describe("dotDiameter", () => {
  it("scales the slot size by DOT_SCALE, rounded to a whole pixel", () => {
    expect(DOT_SCALE).toBe(0.75);
    expect(dotDiameter(11)).toBe(Math.round(11 * DOT_SCALE)); // the default slot -> 8px
    expect(dotDiameter(8)).toBe(6);
    expect(dotDiameter(0)).toBe(0);
  });

  it("keeps the dot inset from the slot edges at every rendered size", () => {
    for (const size of [7, 8, 11]) {
      expect(dotDiameter(size)).toBeLessThan(size);
    }
  });
});
