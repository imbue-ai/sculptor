// Chromium's async clipboard reliably accepts only `image/png` for image
// data, so any non-PNG source is rasterized to PNG before writing.
const convertBlobToPng = async (blob: Blob): Promise<Blob> => {
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Failed to acquire 2D canvas context for PNG conversion");
    }
    context.drawImage(bitmap, 0, 0);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((result) => {
        if (result) {
          resolve(result);
        } else {
          reject(new Error("Canvas toBlob produced no image data"));
        }
      }, "image/png");
    });
  } finally {
    bitmap.close();
  }
};

const fetchImageAsPng = async (url: string): Promise<Blob> => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch image for copy: HTTP ${response.status}`);
  }
  const blob = await response.blob();
  return blob.type === "image/png" ? blob : convertBlobToPng(blob);
};

/**
 * Copy the full-size image at `url` to the system clipboard as a PNG.
 *
 * `url` is expected to be a blob: or data: URL pointing at the original image
 * (not a downscaled thumbnail). A `Promise<Blob>` is handed to `ClipboardItem`
 * so the async fetch/convert work does not break the user-gesture requirement.
 */
export const copyImageToClipboard = async (url: string): Promise<void> => {
  await navigator.clipboard.write([new ClipboardItem({ "image/png": fetchImageAsPng(url) })]);
};
