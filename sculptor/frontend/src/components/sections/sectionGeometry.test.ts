import { describe, expect, it } from "vitest";

import {
  CENTER_MIN_WIDTH_PX,
  resolveSectionPixelSizes,
  SECTION_SIZE_MAX_PERCENT,
  SECTION_SIZE_MIN_PERCENT,
  SIDE_MIN_WIDTH_PX,
  sizeToPercent,
} from "./sectionGeometry.ts";

const SIZES = { left: 20, right: 20, bottom: 30 };

describe("resolveSectionPixelSizes", () => {
  it("uses the stored percentages when the container is wide enough", () => {
    const { leftPx, rightPx, bottomPx } = resolveSectionPixelSizes({
      containerWidth: 2000,
      containerHeight: 1000,
      sizes: SIZES,
      isLeftExpanded: true,
      isRightExpanded: true,
      isBottomExpanded: true,
    });
    expect(leftPx).toBe(400);
    expect(rightPx).toBe(400);
    expect(bottomPx).toBe(300);
  });

  it("shrinks the right side before the left and never below the side floor", () => {
    const { leftPx, rightPx } = resolveSectionPixelSizes({
      containerWidth: 900,
      containerHeight: 1000,
      sizes: { left: 30, right: 30, bottom: 30 },
      isLeftExpanded: true,
      isRightExpanded: true,
      isBottomExpanded: false,
    });
    // 30% of 900 = 270 each; center needs 400 + 2 handles = 402 → deficit 138.
    // Right gives way first, down toward its 150 floor, before the left moves.
    expect(rightPx).toBeLessThan(leftPx);
    expect(rightPx).toBeGreaterThanOrEqual(SIDE_MIN_WIDTH_PX);
    expect(leftPx).toBeGreaterThanOrEqual(SIDE_MIN_WIDTH_PX);
  });

  it("protects the center's minimum width by driving both sides to their floor", () => {
    const { leftPx, rightPx } = resolveSectionPixelSizes({
      containerWidth: CENTER_MIN_WIDTH_PX + 2 * SIDE_MIN_WIDTH_PX + 2,
      containerHeight: 1000,
      sizes: { left: 40, right: 40, bottom: 30 },
      isLeftExpanded: true,
      isRightExpanded: true,
      isBottomExpanded: false,
    });
    expect(leftPx).toBe(SIDE_MIN_WIDTH_PX);
    expect(rightPx).toBe(SIDE_MIN_WIDTH_PX);
  });

  it("returns zero for collapsed sections", () => {
    const { leftPx, rightPx, bottomPx } = resolveSectionPixelSizes({
      containerWidth: 2000,
      containerHeight: 1000,
      sizes: SIZES,
      isLeftExpanded: false,
      isRightExpanded: false,
      isBottomExpanded: false,
    });
    expect(leftPx).toBe(0);
    expect(rightPx).toBe(0);
    expect(bottomPx).toBe(0);
  });
});

describe("sizeToPercent", () => {
  it("converts pixels to a percentage of the dimension", () => {
    expect(sizeToPercent(250, 1000)).toBe(25);
  });

  it("clamps to the allowed percentage range", () => {
    expect(sizeToPercent(10, 1000)).toBe(SECTION_SIZE_MIN_PERCENT);
    expect(sizeToPercent(950, 1000)).toBe(SECTION_SIZE_MAX_PERCENT);
  });

  it("falls back to the minimum when the dimension is unknown", () => {
    expect(sizeToPercent(100, 0)).toBe(SECTION_SIZE_MIN_PERCENT);
  });
});
