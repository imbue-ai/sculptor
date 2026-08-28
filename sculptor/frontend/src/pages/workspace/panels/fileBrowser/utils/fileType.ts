const BINARY_EXTENSIONS = new Set([
  // Images
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "svg",
  "ico",
  "bmp",
  "tiff",
  // Fonts
  "woff",
  "woff2",
  "ttf",
  "otf",
  "eot",
  // Documents
  "pdf",
  // Archives
  "zip",
  "tar",
  "gz",
  // Compiled
  "wasm",
  "pyc",
  "class",
  // Media
  "mp3",
  "mp4",
  "avi",
  "mov",
]);

const SUPPORTED_IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);

const getExtension = (fileName: string): string => {
  const lastDot = fileName.lastIndexOf(".");
  if (lastDot < 0) {
    return "";
  }
  return fileName.slice(lastDot + 1).toLowerCase();
};

export const isBinaryFile = (fileName: string): boolean => {
  return BINARY_EXTENSIONS.has(getExtension(fileName));
};

export const isSupportedImageFormat = (fileName: string): boolean => {
  return SUPPORTED_IMAGE_EXTENSIONS.has(getExtension(fileName));
};
