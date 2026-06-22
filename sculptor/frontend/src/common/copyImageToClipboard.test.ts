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
  // so a rejected fetch/convert propagates to the caller.
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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("copyImageToClipboard", () => {
  it("writes the original blob as image/png when the source is already a PNG", async () => {
    const pngBlob = new Blob(["png-bytes"], { type: "image/png" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(pngBlob) } as Response));
    const write = installClipboardStub();

    await copyImageToClipboard("blob:fake-url");

    expect(write).toHaveBeenCalledTimes(1);
    const [items] = write.mock.calls[0] as [Array<FakeClipboardItem>];
    expect(items).toHaveLength(1);
    expect(Object.keys(items[0].items)).toEqual(["image/png"]);
    await expect(items[0].items["image/png"]).resolves.toBe(pngBlob);
  });

  it("rasterizes a non-PNG source to PNG before writing", async () => {
    const jpegBlob = new Blob(["jpeg-bytes"], { type: "image/jpeg" });
    const pngBlob = new Blob(["png-bytes"], { type: "image/png" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(jpegBlob) } as Response));
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 2, height: 3, close: vi.fn() }));
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

    await copyImageToClipboard("blob:jpeg-url");

    // The source bitmap's own dimensions drive the canvas, and the PNG export is what lands on the clipboard.
    expect(canvasWidth).toBe(2);
    expect(canvasHeight).toBe(3);
    expect(drawImage).toHaveBeenCalledOnce();
    const [items] = write.mock.calls[0] as [Array<FakeClipboardItem>];
    await expect(items[0].items["image/png"]).resolves.toBe(pngBlob);
  });

  it("throws when the fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 } as Response));
    installClipboardStub();

    await expect(copyImageToClipboard("blob:missing")).rejects.toThrow(/404/);
  });
});
