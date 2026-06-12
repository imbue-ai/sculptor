/**
 * Generates a 12-step Radix-like color scale from a single hex color.
 *
 * The input hex is treated as step 9 (the solid background step).
 * Uses HSL color space to preserve hue and saturation while varying lightness,
 * producing vibrant scales that avoid the desaturation of linear RGB mixing.
 */

type Rgb = { r: number; g: number; b: number };
type Hsl = { h: number; s: number; l: number };

const hexToRgb = (hex: string): Rgb => {
  const cleaned = hex.replace("#", "");
  return {
    r: parseInt(cleaned.slice(0, 2), 16),
    g: parseInt(cleaned.slice(2, 4), 16),
    b: parseInt(cleaned.slice(4, 6), 16),
  };
};

const rgbToHex = (rgb: Rgb): string => {
  const toHex = (n: number): string => {
    const clamped = Math.max(0, Math.min(255, Math.round(n)));
    return clamped.toString(16).padStart(2, "0");
  };
  return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`;
};

const rgbToHsl = (rgb: Rgb): Hsl => {
  const r = rgb.r / 255;
  const g = rgb.g / 255;
  const b = rgb.b / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;

  if (max === min) {
    return { h: 0, s: 0, l };
  }

  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;

  if (max === r) {
    h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
  } else if (max === g) {
    h = ((b - r) / d + 2) / 6;
  } else {
    h = ((r - g) / d + 4) / 6;
  }

  return { h, s, l };
};

const hue2rgb = (p: number, q: number, t: number): number => {
  const tn = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
  if (tn < 1 / 6) return p + (q - p) * 6 * tn;
  if (tn < 1 / 2) return q;
  if (tn < 2 / 3) return p + (q - p) * (2 / 3 - tn) * 6;
  return p;
};

const hslToRgb = (hsl: Hsl): Rgb => {
  const { h, s, l } = hsl;

  if (s === 0) {
    const v = Math.round(l * 255);
    return { r: v, g: v, b: v };
  }

  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;

  return {
    r: hue2rgb(p, q, h + 1 / 3) * 255,
    g: hue2rgb(p, q, h) * 255,
    b: hue2rgb(p, q, h - 1 / 3) * 255,
  };
};

/**
 * Light mode: positive ratios interpolate lightness toward near-white,
 * negative ratios toward near-black. Step 9 = input color.
 */
const LIGHT_MODE_RATIOS: ReadonlyArray<number> = [
  0.97, // step 1: very light bg
  0.93, // step 2: subtle bg
  0.86, // step 3: element bg
  0.78, // step 4: hovered element bg
  0.7, // step 5: active element bg
  0.6, // step 6: subtle borders
  0.47, // step 7: element borders
  0.32, // step 8: hovered borders
  0.0, // step 9: solid bg (input color)
  -0.08, // step 10: hovered solid bg
  -0.25, // step 11: low-contrast text
  -0.65, // step 12: high-contrast text
];

/**
 * Dark mode: positive ratios interpolate lightness toward near-black,
 * negative ratios toward near-white. Step 9 = input color.
 */
const DARK_MODE_RATIOS: ReadonlyArray<number> = [
  0.95, // step 1: very dark bg
  0.9, // step 2: subtle bg
  0.82, // step 3: element bg
  0.73, // step 4: hovered element bg
  0.64, // step 5: active element bg
  0.55, // step 6: subtle borders
  0.43, // step 7: element borders
  0.3, // step 8: hovered borders
  0.0, // step 9: solid bg (input color)
  -0.15, // step 10: hovered solid bg (slightly lighter)
  -0.4, // step 11: low-contrast text
  -0.75, // step 12: high-contrast text
];

/** Target lightness for the "light" end of each mode's scale. */
const LIGHT_L = 0.99;
/** Target lightness for the "dark" end of each mode's scale. */
const DARK_L = 0.06;

/**
 * Generate a 12-step color scale from a single hex value.
 * Returns an array of 12 hex strings.
 *
 * Works in HSL space: keeps hue constant and interpolates lightness,
 * preserving saturation across the entire scale.
 */
export const generateColorScale = (hex: string, mode: "light" | "dark"): ReadonlyArray<string> => {
  const base = hexToRgb(hex);
  const baseHsl = rgbToHsl(base);
  const ratios = mode === "light" ? LIGHT_MODE_RATIOS : DARK_MODE_RATIOS;
  const lightEndL = mode === "light" ? LIGHT_L : DARK_L;
  const darkEndL = mode === "light" ? DARK_L : LIGHT_L;

  return ratios.map((ratio) => {
    let targetL: number;
    if (ratio >= 0) {
      targetL = baseHsl.l + (lightEndL - baseHsl.l) * ratio;
    } else {
      targetL = baseHsl.l + (darkEndL - baseHsl.l) * Math.abs(ratio);
    }

    return rgbToHex(hslToRgb({ h: baseHsl.h, s: baseHsl.s, l: targetL }));
  });
};

const HEX_PATTERN = /^#[0-9a-fA-F]{6}$/;

export const isValidHex = (value: string): boolean => HEX_PATTERN.test(value);
