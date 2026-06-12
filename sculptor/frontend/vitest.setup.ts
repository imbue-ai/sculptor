import "@testing-library/jest-dom/vitest";

import { createRequire } from "node:module";

// Pierre diffs uses CSSStyleSheet.replaceSync for shadow DOM styling, which jsdom
// does not implement. Provide a no-op polyfill so module-level init doesn't crash.
if (typeof CSSStyleSheet.prototype.replaceSync !== "function") {
  CSSStyleSheet.prototype.replaceSync = function (): void {};
}

// xterm's WebglAddon calls HTMLCanvasElement.prototype.getContext, which jsdom
// only implements via the optional `canvas` npm package. When that package is
// absent jsdom falls back to a stub that returns null but emits a noisy
// "Not implemented" line on every call. Replace the stub with a silent no-op
// only in that case — if `canvas` is installed, the real implementation stays.
try {
  createRequire(import.meta.url).resolve("canvas");
} catch {
  HTMLCanvasElement.prototype.getContext = (() => null) as HTMLCanvasElement["getContext"];
}

// react-resizable-panels requires ResizeObserver, which is not available in jsdom.
global.ResizeObserver = class {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
};

// Radix UI's floating-ui uses DOMRect.fromRect for context menu positioning.
// jsdom does not implement DOMRect, so we provide a minimal polyfill.
if (typeof globalThis.DOMRect === "undefined") {
  globalThis.DOMRect = class DOMRect {
    x: number;
    y: number;
    width: number;
    height: number;
    top: number;
    right: number;
    bottom: number;
    left: number;

    constructor(x = 0, y = 0, width = 0, height = 0) {
      this.x = x;
      this.y = y;
      this.width = width;
      this.height = height;
      this.top = y;
      this.right = x + width;
      this.bottom = y + height;
      this.left = x;
    }

    toJSON(): Record<string, number> {
      return {
        x: this.x,
        y: this.y,
        width: this.width,
        height: this.height,
        top: this.top,
        right: this.right,
        bottom: this.bottom,
        left: this.left,
      };
    }

    static fromRect(rect?: { x?: number; y?: number; width?: number; height?: number }): DOMRect {
      return new DOMRect(rect?.x, rect?.y, rect?.width, rect?.height);
    }
  } as unknown as typeof DOMRect;
}
