/**
 * Dev-mode icon generation.
 *
 * When running from source the production icon is inverted and hue-shifted
 * (based on the working directory) so that each checkout gets a visually
 * distinct, consistent icon.  Two text overlays are rendered on top:
 *   - A larger label at the top (e.g. "src", "pytest")
 *   - A smaller port number at the bottom (e.g. "8080")
 *
 * Everything in this module is gated on `!app.isPackaged` by the caller in
 * main.ts — none of this code runs in production builds.
 */

import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

import { nativeImage } from "electron";
import { PNG } from "pngjs";
import * as PImage from "pureimage";

import { logger } from "./logger";

/**
 * Well-known monospace font paths per platform.  Checked first before falling
 * back to `fc-list` on Linux.
 */
const FONT_CANDIDATES: Record<string, Array<string>> = {
  darwin: ["/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc"],
  linux: [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
  ],
};

function findFont(): string | null {
  // Try well-known paths first.
  for (const candidate of FONT_CANDIDATES[process.platform] ?? []) {
    if (fs.existsSync(candidate)) return candidate;
  }

  // On Linux, ask fontconfig for any monospace .ttf file.
  if (process.platform === "linux") {
    try {
      const result = execSync('fc-list :spacing=mono:fontformat=TrueType -f "%{file}\\n"', {
        encoding: "utf-8",
        timeout: 2000,
      });
      const first = result.split("\n").find((l) => l.endsWith(".ttf"));
      if (first) return first;
    } catch {
      // fontconfig not available — give up on text.
    }
  }

  return null;
}

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

function hue2rgb(p: number, q: number, t: number): number {
  const tt = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
  if (tt < 1 / 6) return p + (q - p) * 6 * tt;
  if (tt < 1 / 2) return q;
  if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
  return p;
}

/**
 * Invert and hue-shift an RGBA bitmap buffer in-place.
 * Alpha channel is preserved; fully transparent pixels are skipped.
 */
function invertAndHueShift(bitmap: Buffer, hueShift: number): void {
  for (let i = 0; i < bitmap.length; i += 4) {
    if (bitmap[i + 3] === 0) continue; // preserve fully transparent pixels

    const r = (255 - bitmap[i]) / 255;
    const g = (255 - bitmap[i + 1]) / 255;
    const b = (255 - bitmap[i + 2]) / 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;
    let h = 0;
    let s = 0;

    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
      else if (max === g) h = ((b - r) / d + 2) / 6;
      else h = ((r - g) / d + 4) / 6;
    }

    h = (h + hueShift) % 1;

    let nr: number, ng: number, nb: number;
    if (s === 0) {
      nr = ng = nb = l;
    } else {
      const q2 = l < 0.5 ? l * (1 + s) : l + s - l * s;
      const p2 = 2 * l - q2;
      nr = hue2rgb(p2, q2, h + 1 / 3);
      ng = hue2rgb(p2, q2, h);
      nb = hue2rgb(p2, q2, h - 1 / 3);
    }

    bitmap[i] = Math.round(nr * 255);
    bitmap[i + 1] = Math.round(ng * 255);
    bitmap[i + 2] = Math.round(nb * 255);
  }
}

/**
 * Render text overlays onto the icon bitmap:
 *   - `label` in a larger white font near the top (no background rectangle,
 *     shifted down slightly so it overlaps the icon body)
 *   - `port`  in a smaller black font near the bottom (no background)
 *
 * If no suitable font is found on the system, returns the bitmap unchanged
 * (the color-shifted icon is still useful without text).
 */
function renderTextOverlays(
  bitmap: Buffer,
  width: number,
  height: number,
  label: string | undefined,
  port: string | undefined,
): Buffer {
  if (!label && !port) return bitmap;

  const fontPath = findFont();
  if (!fontPath) {
    logger.warn("[devIcon] No suitable font found — skipping text overlays");
    return bitmap;
  }

  const img = PImage.make(width, height);
  for (let i = 0; i < bitmap.length; i++) {
    img.data[i] = bitmap[i];
  }

  const ctx = img.getContext("2d");
  const fontName = "DevIconFont";
  const font = PImage.registerFont(fontPath, fontName);
  font.loadSync();

  // Scale relative to the icon (tuned for 1024px source icon).
  const scale = width / 1024;

  if (label) {
    const fontSize = Math.round(scale * 140);
    const stripHeight = Math.round(fontSize * 1.7);
    const textShift = Math.round(scale * 30);
    ctx.font = `${fontSize}pt ${fontName}`;
    const metrics = ctx.measureText(label);
    const textX = Math.round((width - metrics.width) / 2);
    const textY = Math.round(stripHeight * 0.72) + textShift;
    ctx.fillStyle = "white";
    ctx.fillText(label, textX, textY);
  }

  if (port) {
    const fontSize = Math.round(scale * 90);
    const stripHeight = Math.round(fontSize * 1.7);
    const stripY = height - stripHeight;
    const textY = Math.round(stripY + stripHeight * 0.72) - stripHeight + Math.round(fontSize * 0.5);
    ctx.font = `${fontSize}pt ${fontName}`;
    const metrics = ctx.measureText(port);
    const textX = Math.round((width - metrics.width) / 2);
    ctx.fillStyle = "black";
    ctx.fillText(port, textX, textY);
  }

  return Buffer.from(img.data);
}

type DevIconOptions = {
  /** Large label rendered at the top of the icon (e.g. "src", "pytest"). */
  label?: string;
  /** Smaller port number rendered at the bottom (e.g. "8080"). */
  port?: string;
};

/**
 * Create a dev-mode icon: inverted + hue-shifted, with optional text overlays.
 * Returns null if the source icon is missing or an unexpected error occurs
 * (this must never prevent the app from starting).
 */
export function createDevIcon(options: DevIconOptions): Electron.NativeImage | null {
  try {
    const iconPath = path.join(__dirname, "..", "..", "assets", "desktop_icon.png");
    if (!fs.existsSync(iconPath)) {
      return null;
    }

    // Read the PNG via pngjs to get a clean RGBA buffer (nativeImage.toBitmap()
    // returns BGRA on some platforms, so we avoid that ambiguity).
    const pngData = PNG.sync.read(fs.readFileSync(iconPath));
    const { width, height } = pngData;
    let bitmap = pngData.data;

    const hueShift = (hashString(process.cwd()) % 360) / 360;
    invertAndHueShift(bitmap, hueShift);

    bitmap = renderTextOverlays(bitmap, width, height, options.label, options.port);

    const outPng = new PNG({ width, height });
    outPng.data = bitmap;
    const pngBuffer = PNG.sync.write(outPng);
    return nativeImage.createFromBuffer(pngBuffer);
  } catch (error) {
    logger.error("[devIcon] Failed to generate dev icon:", error);
    return null;
  }
}
