import { afterEach, describe, expect, it, vi } from "vitest";

import { copyImageToClipboard } from "./copyImageToClipboard";

class FakeClipboardItem {
  items: Record<string, Blob | Promise<Blob>>;
  constructor(items: Record<string, Blob | Promise<Blob>>) {
    this.items = items;
  }
}

const installClipboardStub = (): ReturnType<typeof vi.fn> => {
  // Mirror real clipboard.write semantics: resolve the per-type blob promises
  // so a rejected decode/encode propagates to the caller.
  const write = vi.fn(async (items: Array<FakeClipboardItem>): Promise<void> => {
    for (const item of items) {
      await Promise.all(Object.values(item.items));
    }
  });
  vi.stubGlobal("ClipboardItem", FakeClipboardItem);
  Object.defineProperty(globalThis.navigator, "clipboard", {
    value: { write },
    configurable: true,
  });
  return write;
};

// jsdom doesn't load <img> sources, so fake Image: setting `src` resolves
// onload (or onerror) on the next microtask with the given intrinsic size.
const stubImage = (options: { width: number; height: number; fail?: boolean }): void => {
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    naturalWidth = 0;
    naturalHeight = 0;
    set src(_value: string) {
      queueMicrotask(() => {
        if (options.fail) {
          this.onerror?.();
          return;
        }
        this.naturalWidth = options.width;
        this.naturalHeight = options.height;
        this.onload?.();
      });
    }
  }
  vi.stubGlobal("Image", FakeImage);
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("copyImageToClipboard", () => {
  it("rasterizes the source image to PNG at full resolution and writes it to the clipboard", async () => {
    const pngBlob = new Blob(["png-bytes"], { type: "image/png" });
    stubImage({ width: 4, height: 6 });
    const drawImage = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage,
    } as unknown as CanvasRenderingContext2D);
    let canvasWidth: number | undefined;
    let canvasHeight: number | undefined;
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (
      this: HTMLCanvasElement,
      callback: BlobCallback,
      type?: string,
    ): void {
      canvasWidth = this.width;
      canvasHeight = this.height;
      expect(type).toBe("image/png");
      callback(pngBlob);
    });
    const write = installClipboardStub();

    await copyImageToClipboard("blob:some-image");

    // The image's intrinsic dimensions drive the canvas (full resolution),
    // and the PNG export is what lands on the clipboard.
    expect(canvasWidth).toBe(4);
    expect(canvasHeight).toBe(6);
    expect(drawImage).toHaveBeenCalledOnce();
    expect(write).toHaveBeenCalledTimes(1);
    const [items] = write.mock.calls[0] as [Array<FakeClipboardItem>];
    expect(Object.keys(items[0].items)).toEqual(["image/png"]);
    await expect(items[0].items["image/png"]).resolves.toBe(pngBlob);
  });

  it("rejects when the source image cannot be loaded", async () => {
    stubImage({ width: 0, height: 0, fail: true });
    installClipboardStub();

    await expect(copyImageToClipboard("blob:broken")).rejects.toThrow(/could not be loaded/);
  });
});
