import { describe, expect, it } from "vitest";

import {
  CATCHUP_BUFFER_CHARS,
  computeDrainStep,
  DEFAULT_DRAIN_WINDOW_MS,
  MAX_CHARS_PER_FRAME,
  MAX_DRAIN_WINDOW_MS,
  MIN_CATCHUP_WINDOW_MS,
  MIN_DRAIN_WINDOW_MS,
  resolveBaseDrainWindowMs,
  resolveEffectiveDrainWindowMs,
  RUNAWAY_BUFFER_CHARS,
  snapToWordBoundary,
  updateDeliveryIntervalEma,
} from "./smoothStreamingDrain.ts";

describe("resolveBaseDrainWindowMs", () => {
  it("falls back to the default before any cadence is observed", () => {
    expect(resolveBaseDrainWindowMs(null)).toBe(DEFAULT_DRAIN_WINDOW_MS);
  });

  it("clamps into the [MIN, MAX] band", () => {
    expect(resolveBaseDrainWindowMs(10)).toBe(MIN_DRAIN_WINDOW_MS);
    expect(resolveBaseDrainWindowMs(99999)).toBe(MAX_DRAIN_WINDOW_MS);
    expect(resolveBaseDrainWindowMs(500)).toBe(500);
  });
});

describe("resolveEffectiveDrainWindowMs", () => {
  it("leaves the window unchanged below the catch-up threshold", () => {
    expect(resolveEffectiveDrainWindowMs(400, 100)).toBe(400);
    expect(resolveEffectiveDrainWindowMs(400, CATCHUP_BUFFER_CHARS)).toBe(400);
  });

  it("compresses the window monotonically as the buffer grows past the threshold", () => {
    const base = 400;
    const small = resolveEffectiveDrainWindowMs(base, CATCHUP_BUFFER_CHARS + 100);
    const larger = resolveEffectiveDrainWindowMs(base, CATCHUP_BUFFER_CHARS + 500);
    expect(small).toBeLessThan(base);
    expect(larger).toBeLessThan(small);
    expect(larger).toBeGreaterThanOrEqual(MIN_CATCHUP_WINDOW_MS);
  });

  it("bottoms out at the catch-up floor near the runaway threshold", () => {
    const base = 400;
    expect(resolveEffectiveDrainWindowMs(base, RUNAWAY_BUFFER_CHARS)).toBeCloseTo(MIN_CATCHUP_WINDOW_MS, 5);
  });
});

describe("computeDrainStep", () => {
  it("reveals nothing when the buffer is empty", () => {
    expect(computeDrainStep(0, 16, null)).toEqual({ charsToReveal: 0, shouldFlush: false });
  });

  it("flushes on a runaway buffer", () => {
    const buffer = RUNAWAY_BUFFER_CHARS + 500;
    expect(computeDrainStep(buffer, 16, null)).toEqual({ charsToReveal: buffer, shouldFlush: true });
  });

  it("always makes at least one character of progress", () => {
    // Tiny buffer, tiny elapsed — still reveals at least one char.
    const step = computeDrainStep(3, 1, MAX_DRAIN_WINDOW_MS);
    expect(step.shouldFlush).toBe(false);
    expect(step.charsToReveal).toBeGreaterThanOrEqual(1);
  });

  it("never reveals more than the per-frame cap even for a fast large stream", () => {
    // Large buffer + short window would ask for a big chunk; the cap prevents it.
    const step = computeDrainStep(CATCHUP_BUFFER_CHARS, 16, MIN_DRAIN_WINDOW_MS);
    expect(step.shouldFlush).toBe(false);
    expect(step.charsToReveal).toBeLessThanOrEqual(MAX_CHARS_PER_FRAME);
  });

  it("caps the elapsed time so a long idle frame does not dump the buffer", () => {
    // A multi-second elapsed (background-tab resume) should behave like the cap,
    // not reveal thousands of chars.
    const idle = computeDrainStep(200, 10_000, DEFAULT_DRAIN_WINDOW_MS);
    expect(idle.shouldFlush).toBe(false);
    expect(idle.charsToReveal).toBeLessThanOrEqual(MAX_CHARS_PER_FRAME);
  });
});

describe("snapToWordBoundary", () => {
  it("returns the raw value when the target is at or past the text end", () => {
    const text = "hello";
    expect(snapToWordBoundary(text, 0, 10)).toBe(10);
  });

  it("returns the raw value when the target already lands on a boundary", () => {
    const text = "hello world";
    // offset 0, reveal 5 -> targets index 5 which is a space.
    expect(snapToWordBoundary(text, 0, 5)).toBe(5);
  });

  it("snaps forward to the next boundary when it is closer", () => {
    const text = "hello world foo";
    // offset 0 reveal 4 -> target index 4 ('o'), nearest boundary is the space
    // at index 5 (distance 1 forward) vs none behind within range.
    expect(snapToWordBoundary(text, 0, 4)).toBe(5);
  });

  it("snaps backward to the previous boundary when it is closer", () => {
    const text = "ab cdefghij";
    // offset 0, reveal 8 -> target index 8 (mid 'cdefghij'); the space at index 2
    // is the previous boundary. Forward has no boundary within lookahead, so it
    // rounds down to the space, making progress of 2 chars.
    expect(snapToWordBoundary(text, 0, 8)).toBe(2);
  });

  it("never regresses past the current offset", () => {
    const text = "abcdefghij";
    // No boundaries at all -> raw value preserved.
    expect(snapToWordBoundary(text, 3, 4)).toBe(4);
  });
});

describe("updateDeliveryIntervalEma", () => {
  it("initializes to the first observed gap", () => {
    expect(updateDeliveryIntervalEma(null, 200)).toBe(200);
  });

  it("smooths toward newer gaps", () => {
    const next = updateDeliveryIntervalEma(200, 400);
    expect(next).toBeGreaterThan(200);
    expect(next).toBeLessThan(400);
  });

  it("ignores stall-sized gaps and keeps the previous EMA", () => {
    expect(updateDeliveryIntervalEma(200, 999_999)).toBe(200);
    expect(updateDeliveryIntervalEma(null, 999_999)).toBeNull();
  });
});
