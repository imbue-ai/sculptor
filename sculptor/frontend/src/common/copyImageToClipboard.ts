// Load the image the same way the browser renders it in an <img>, then
// rasterize to PNG. Chromium's async clipboard only reliably accepts image/png,
// and an <img>-backed decode handles every format the UI can display (jpeg,
// webp, gif, svg, …). `createImageBitmap` is stricter and rejects some of those
// with "the source image could not be decoded", even when the thumbnail shows.
const loadImageElement = (url: string): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = (): void => resolve(image);
    image.onerror = (): void => reject(new Error("The source image could not be loaded for copying"));
    image.src = url;
  });

const rasterizeToPng = async (url: string): Promise<Blob> => {
  const image = await loadImageElement(url);
  if (image.naturalWidth === 0 || image.naturalHeight === 0) {
    throw new Error("The source image has no intrinsic dimensions to rasterize");
  }
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Failed to acquire 2D canvas context for PNG conversion");
  }
  context.drawImage(image, 0, 0);
  return await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((result) => {
      if (result) {
        resolve(result);
      } else {
        reject(new Error("Canvas toBlob produced no image data"));
      }
    }, "image/png");
  });
};

/**
 * Copy the full-size image at `url` to the system clipboard as a PNG.
 *
 * `url` is the same blob:/data: URL the chat renders in its <img>, so the copy
 * is full resolution (the image's intrinsic size, not the scaled thumbnail). A
 * `Promise<Blob>` is handed to `ClipboardItem` so the async decode/encode does
 * not break the user-gesture requirement.
 */
export const copyImageToClipboard = async (url: string): Promise<void> => {
  await navigator.clipboard.write([new ClipboardItem({ "image/png": rasterizeToPng(url) })]);
};
