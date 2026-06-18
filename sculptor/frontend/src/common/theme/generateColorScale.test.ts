import { describe, expect, it } from "vitest";

import { generateColorScale, isValidHex } from "./generateColorScale.ts";

describe("isValidHex", () => {
  it("accepts valid 6-digit hex codes", () => {
    expect(isValidHex("#000000")).toBe(true);
    expect(isValidHex("#ffffff")).toBe(true);
    expect(isValidHex("#0090ff")).toBe(true);
    expect(isValidHex("#ABCDEF")).toBe(true);
  });

  it("rejects invalid hex codes", () => {
    expect(isValidHex("000000")).toBe(false);
    expect(isValidHex("#fff")).toBe(false);
    expect(isValidHex("#gggggg")).toBe(false);
    expect(isValidHex("")).toBe(false);
  });
});

describe("generateColorScale", () => {
  it("returns 12 hex strings", () => {
    const scale = generateColorScale("#0090ff", "light");
    expect(scale).toHaveLength(12);
    for (const hex of scale) {
      expect(hex).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it("step 9 equals the input color", () => {
    expect(generateColorScale("#0090ff", "light")[8]).toBe("#0090ff");
    expect(generateColorScale("#0090ff", "dark")[8]).toBe("#0090ff");
    expect(generateColorScale("#e54d2e", "light")[8]).toBe("#e54d2e");
    expect(generateColorScale("#e54d2e", "dark")[8]).toBe("#e54d2e");
  });

  describe("light mode produces correct scale direction", () => {
    it("steps 1-8 are lighter than step 9", () => {
      const scale = generateColorScale("#0090ff", "light");
      const step9Rgb = hexToRgbSum(scale[8]);
      for (let i = 0; i < 8; i++) {
        // Lighter colors have higher RGB sum (closer to white)
        expect(hexToRgbSum(scale[i])).toBeGreaterThan(step9Rgb);
      }
    });

    it("steps 10-12 are darker than step 9", () => {
      const scale = generateColorScale("#0090ff", "light");
      const step9Rgb = hexToRgbSum(scale[8]);
      for (let i = 9; i < 12; i++) {
        expect(hexToRgbSum(scale[i])).toBeLessThan(step9Rgb);
      }
    });
  });

  describe("dark mode produces correct scale direction", () => {
    it("steps 1-8 are darker than step 9", () => {
      const scale = generateColorScale("#0090ff", "dark");
      const step9Rgb = hexToRgbSum(scale[8]);
      for (let i = 0; i < 8; i++) {
        // Darker colors have lower RGB sum (closer to black)
        expect(hexToRgbSum(scale[i])).toBeLessThan(step9Rgb);
      }
    });

    it("steps 10-12 are lighter than step 9", () => {
      const scale = generateColorScale("#0090ff", "dark");
      const step9Rgb = hexToRgbSum(scale[8]);
      for (let i = 9; i < 12; i++) {
        expect(hexToRgbSum(scale[i])).toBeGreaterThan(step9Rgb);
      }
    });

    it("step 1 is very dark (close to black)", () => {
      const scale = generateColorScale("#0090ff", "dark");
      // Step 1 should be very close to near-black (#111111)
      const sum = hexToRgbSum(scale[0]);
      expect(sum).toBeLessThan(100); // RGB sum < 100 means very dark
    });

    it("step 12 is quite light (readable text on dark bg)", () => {
      const scale = generateColorScale("#0090ff", "dark");
      // Step 12 should be light enough for text
      const sum = hexToRgbSum(scale[11]);
      expect(sum).toBeGreaterThan(450); // RGB sum > 450 means quite light
    });
  });

  describe("scale is monotonic", () => {
    it("light mode: steps 1-9 decrease in lightness, steps 9-12 decrease", () => {
      const scale = generateColorScale("#30a46c", "light");
      for (let i = 0; i < 8; i++) {
        expect(hexToRgbSum(scale[i])).toBeGreaterThan(hexToRgbSum(scale[i + 1]));
      }

      for (let i = 8; i < 11; i++) {
        expect(hexToRgbSum(scale[i])).toBeGreaterThan(hexToRgbSum(scale[i + 1]));
      }
    });

    it("dark mode: steps 1-9 increase in lightness, steps 9-12 increase", () => {
      const scale = generateColorScale("#30a46c", "dark");
      for (let i = 0; i < 8; i++) {
        expect(hexToRgbSum(scale[i])).toBeLessThan(hexToRgbSum(scale[i + 1]));
      }

      for (let i = 8; i < 11; i++) {
        expect(hexToRgbSum(scale[i])).toBeLessThan(hexToRgbSum(scale[i + 1]));
      }
    });
  });
});

/** Helper: sum of RGB channels (rough proxy for lightness). */
const hexToRgbSum = (hex: string): number => {
  const cleaned = hex.replace("#", "");
  const r = parseInt(cleaned.slice(0, 2), 16);
  const g = parseInt(cleaned.slice(2, 4), 16);
  const b = parseInt(cleaned.slice(4, 6), 16);
  return r + g + b;
};
