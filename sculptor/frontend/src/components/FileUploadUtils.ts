import { baseUrl } from "~/apiClient.ts";
import { setupAuthHeaders } from "~/common/Auth.ts";
import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB
// NOTE: we can support PDF uploads but Claude Code can not read PDFs
const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".gif"] as const; // ".pdf"
const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"] as const;

export const validateFile = (file: File): { valid: boolean; error?: string } => {
  if (file.size > MAX_FILE_SIZE) {
    return {
      valid: false,
      error: `"${file.name}" exceeds 20MB limit (${(file.size / 1024 / 1024).toFixed(1)}MB)`,
    };
  }

  const fileNameLower = file.name.toLowerCase();
  const hasValidExtension = ALLOWED_EXTENSIONS.some((ext) => fileNameLower.endsWith(ext));
  if (!hasValidExtension) {
    return {
      valid: false,
      error: `"${file.name}" has invalid extension. Allowed: ${ALLOWED_EXTENSIONS.join(", ")}`,
    };
  }

  if (!ALLOWED_MIME_TYPES.includes(file.type as (typeof ALLOWED_MIME_TYPES)[number])) {
    return {
      valid: false,
      error: `"${file.name}" has invalid type (${file.type}). Allowed: ${ALLOWED_MIME_TYPES.join(", ")}`,
    };
  }

  return { valid: true };
};

/**
 * Validates that an ArrayBuffer contains valid file data by checking magic bytes.
 */
export const validateFileData = (arrayBuffer: ArrayBuffer, fileName: string): { valid: boolean; error?: string } => {
  const bytes = new Uint8Array(arrayBuffer);

  if (bytes.byteLength === 0) {
    return { valid: false, error: `"${fileName}" is empty` };
  }

  if (bytes.byteLength < 10) {
    return { valid: false, error: `"${fileName}" appears to be corrupted (too small)` };
  }

  // Helper to match a sequence
  const match = (offset: number, signature: Array<number>): boolean =>
    signature.every((b, i) => bytes[offset + i] === b);

  const signatures = {
    PNG: [0x89, 0x50, 0x4e, 0x47],
    JPEG: [0xff, 0xd8, 0xff],
    GIF: [0x47, 0x49, 0x46],
    WEBP: [0x57, 0x45, 0x42, 0x50],
  };

  const isPNG = match(0, signatures.PNG);
  const isJPEG = match(0, signatures.JPEG);
  const isGIF = match(0, signatures.GIF);
  const isWEBP = match(8, signatures.WEBP);

  if (!(isPNG || isJPEG || isGIF || isWEBP)) {
    return { valid: false, error: `"${fileName}" is not a recognized file format` };
  }

  return { valid: true };
};

/**
 * Validates that a file is actually a valid file by reading its magic bytes
 */
export const validateFileContent = async (file: File): Promise<{ valid: boolean; error?: string }> => {
  try {
    // Read first 100 bytes to check magic numbers
    const buffer = await file.slice(0, 100).arrayBuffer();
    return validateFileData(buffer, file.name);
  } catch (error) {
    console.error("Failed to validate file content:", error);
    return {
      valid: false,
      error: `"${file.name}" could not be validated`,
    };
  }
};

/**
 * Process and validate multiple files, returning valid file paths and errors
 */
export const processAndValidateFiles = async (
  filesToUpload: FileList | Array<File>,
): Promise<{
  validFiles: Array<File>;
  errors: Array<string>;
}> => {
  const validationErrors: Array<string> = [];

  const metadataValidFiles = Array.from(filesToUpload).filter((file) => {
    const validation = validateFile(file);
    if (!validation.valid) {
      validationErrors.push(validation.error!);
      return false;
    }
    return true;
  });

  const contentValidationPromises = metadataValidFiles.map(async (file) => {
    const contentValidation = await validateFileContent(file);
    return { file, validation: contentValidation };
  });

  const contentValidationResults = await Promise.all(contentValidationPromises);

  const validFiles = contentValidationResults
    .filter((result) => {
      if (!result.validation.valid) {
        validationErrors.push(result.validation.error!);
        return false;
      }
      return true;
    })
    .map((result) => result.file);

  return { validFiles, errors: validationErrors };
};

const uploadFilesToBackend = async (files: Array<File>): Promise<Array<string>> => {
  const filePromises = files.map(async (file) => {
    try {
      const formData = new FormData();
      formData.append("file", file);

      const headers = new Headers();
      setupAuthHeaders(headers);

      const response = await fetch(`${baseUrl}/api/v1/upload-file`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!response.ok) {
        console.error(`Upload failed for ${file.name}: ${response.status}`);
        return null;
      }

      const data = (await response.json()) as { fileId: string };
      return data.fileId;
    } catch (error) {
      console.error("Failed to upload file:", error);
      return null;
    }
  });

  const results = await Promise.all(filePromises);
  return results.filter((id): id is string => id != null);
};

/**
 * Save files using the window.sculptor API or HTTP upload depending on backend capabilities.
 */
export const saveFiles = async (files: Array<File>): Promise<Array<string>> => {
  if (getBackendCapabilities().fileUploadMode === "http") {
    return uploadFilesToBackend(files);
  }

  const filePromises = files.map(async (file) => {
    try {
      const arrayBuffer = await file.arrayBuffer();

      if (window.sculptor?.saveFile) {
        return await window.sculptor.saveFile(arrayBuffer, file.name);
      }

      return null;
    } catch (error) {
      console.error("Failed to save file:", error);
      return null;
    }
  });

  const savedFilePaths = await Promise.all(filePromises);
  return savedFilePaths.filter((path): path is string => path !== null);
};

export { ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES };
