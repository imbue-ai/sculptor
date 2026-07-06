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

// The Placeholder extension in @tiptap/extensions (since 3.21) tracks the
// visible viewport via EditorView.posAtCoords, which needs
// document.elementFromPoint — jsdom has no layout and does not implement it.
// Returning null makes posAtCoords bail out, so the plugin falls back to the
// full-document scan it used before viewport tracking existed.
if (typeof document.elementFromPoint !== "function") {
  Document.prototype.elementFromPoint = (): Element | null => null;
}

// react-resizable-panels requires ResizeObserver, which is not available in jsdom.
global.ResizeObserver = class {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
};

// Radix UI menus (and their submenus) drive open/close through Pointer Capture
// and scroll focused items into view. jsdom implements none of these, so under
// user-event interactions Radix menus never open. Provide no-op polyfills.
const noop = (): void => undefined;
if (typeof Element.prototype.hasPointerCapture !== "function") {
  Element.prototype.hasPointerCapture = (): boolean => false;
  Element.prototype.setPointerCapture = noop;
  Element.prototype.releasePointerCapture = noop;
}

if (typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = noop;
}

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

// jsdom does not implement DataTransfer or ClipboardEvent. Provide minimal polyfills.
if (typeof globalThis.DataTransfer === "undefined") {
  class MinimalDataTransfer {
    private data = new Map<string, string>();
    get types(): ReadonlyArray<string> {
      return Array.from(this.data.keys());
    }
    setData(type: string, value: string): void {
      this.data.set(type, value);
    }
    getData(type: string): string {
      return this.data.get(type) ?? "";
    }
  }
  (globalThis as { DataTransfer: typeof DataTransfer }).DataTransfer =
    MinimalDataTransfer as unknown as typeof DataTransfer;
}

if (typeof globalThis.ClipboardEvent === "undefined") {
  class MinimalClipboardEvent extends Event {
    clipboardData: DataTransfer | null;
    constructor(type: string, init?: { bubbles?: boolean; cancelable?: boolean; clipboardData?: DataTransfer | null }) {
      super(type, { bubbles: init?.bubbles, cancelable: init?.cancelable });
      this.clipboardData = init?.clipboardData ?? null;
    }
  }
  (globalThis as { ClipboardEvent: typeof ClipboardEvent }).ClipboardEvent =
    MinimalClipboardEvent as unknown as typeof ClipboardEvent;
}
