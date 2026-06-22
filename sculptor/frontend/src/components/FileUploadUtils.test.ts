import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiClientModule from "~/apiClient.ts";
import { initBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";

import {
  ALLOWED_EXTENSIONS,
  ALLOWED_MIME_TYPES,
  processAndValidateFiles,
  saveFiles,
  validateFile,
  validateFileContent,
  validateFileData,
} from "./FileUploadUtils";

// uploadFilesToBackend builds `${baseUrl}/api/v1/upload-file`. Pin baseUrl to a
// known origin so the http-mode test can assert the whole URL — and would fail
// if baseUrl were ever undefined (e.g. "undefined/api/v1/upload-file").
const { TEST_BASE_URL } = vi.hoisted(() => ({ TEST_BASE_URL: "https://backend.test" }));
vi.mock("~/apiClient.ts", async (importOriginal) => ({
  ...(await importOriginal<typeof ApiClientModule>()),
  baseUrl: TEST_BASE_URL,
}));

// jsdom's Blob doesn't implement arrayBuffer(), so polyfill it for tests
beforeAll(() => {
  if (Blob.prototype.arrayBuffer === undefined) {
    Blob.prototype.arrayBuffer = function (): Promise<ArrayBuffer> {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (): void => resolve(reader.result as ArrayBuffer);
        reader.onerror = (): void => reject(reader.error);
        reader.readAsArrayBuffer(this);
      });
    };
  }
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (window as unknown as Record<string, unknown>).sculptor;
});

const createFile = (name: string, size: number, type: string): File => {
  const content = new Uint8Array(size);
  return new File([content], name, { type });
};

const createFileWithContent = (name: string, content: Uint8Array<ArrayBuffer>, type: string): File => {
  return new File([content], name, { type });
};

// PNG magic bytes: 0x89 0x50 0x4E 0x47 ...
const PNG_HEADER = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d]);
// JPEG magic bytes: 0xFF 0xD8 0xFF ...
const JPEG_HEADER = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x00]);
// GIF magic bytes: 0x47 0x49 0x46 ...
const GIF_HEADER = new Uint8Array([0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00, 0x80, 0x00]);
// WEBP magic bytes: RIFF....WEBP (WEBP signature starts at offset 8)
const WEBP_HEADER = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0x00, 0x00, 0x00, 0x00, 0x57, 0x45, 0x42, 0x50]);

describe("validateFile", () => {
  it("accepts a valid PNG file", () => {
    const file = createFile("photo.png", 1024, "image/png");
    expect(validateFile(file)).toEqual({ valid: true });
  });

  it("accepts a valid JPEG file", () => {
    const file = createFile("photo.jpg", 1024, "image/jpeg");
    expect(validateFile(file)).toEqual({ valid: true });
  });

  it("accepts a valid WEBP file", () => {
    const file = createFile("photo.webp", 1024, "image/webp");
    expect(validateFile(file)).toEqual({ valid: true });
  });

  it("accepts a valid GIF file", () => {
    const file = createFile("animation.gif", 1024, "image/gif");
    expect(validateFile(file)).toEqual({ valid: true });
  });

  it("accepts .jpeg extension", () => {
    const file = createFile("photo.jpeg", 1024, "image/jpeg");
    expect(validateFile(file)).toEqual({ valid: true });
  });

  it("rejects file exceeding 20MB limit", () => {
    const file = createFile("huge.png", 21 * 1024 * 1024, "image/png");
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('"huge.png"');
    expect(result.error).toContain("exceeds 20MB limit");
  });

  it("accepts file exactly at 20MB limit", () => {
    const file = createFile("big.png", 20 * 1024 * 1024, "image/png");
    expect(validateFile(file)).toEqual({ valid: true });
  });

  it("rejects unsupported file extension", () => {
    const file = createFile("document.txt", 100, "text/plain");
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('"document.txt"');
    expect(result.error).toContain("invalid extension");
  });

  it("rejects PDF files", () => {
    const file = createFile("document.pdf", 100, "application/pdf");
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("invalid extension");
  });

  it("rejects file with valid extension but wrong MIME type", () => {
    const file = createFile("fake.png", 100, "text/plain");
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("invalid type");
    expect(result.error).toContain("text/plain");
  });

  it("handles case-insensitive extension matching", () => {
    const file = createFile("PHOTO.PNG", 1024, "image/png");
    expect(validateFile(file)).toEqual({ valid: true });
  });

  it("includes file name in size error message", () => {
    const file = createFile("big_image.jpg", 25 * 1024 * 1024, "image/jpeg");
    const result = validateFile(file);
    expect(result.error).toContain('"big_image.jpg"');
  });
});

describe("validateFileData", () => {
  it("accepts valid PNG data", () => {
    expect(validateFileData(PNG_HEADER.buffer, "test.png")).toEqual({ valid: true });
  });

  it("accepts valid JPEG data", () => {
    expect(validateFileData(JPEG_HEADER.buffer, "test.jpg")).toEqual({ valid: true });
  });

  it("accepts valid GIF data", () => {
    expect(validateFileData(GIF_HEADER.buffer, "test.gif")).toEqual({ valid: true });
  });

  it("accepts valid WEBP data", () => {
    expect(validateFileData(WEBP_HEADER.buffer, "test.webp")).toEqual({ valid: true });
  });

  it("rejects empty file", () => {
    const result = validateFileData(new ArrayBuffer(0), "empty.png");
    expect(result.valid).toBe(false);
    expect(result.error).toContain('"empty.png"');
    expect(result.error).toContain("empty");
  });

  it("rejects file that is too small", () => {
    const result = validateFileData(new Uint8Array([0x89, 0x50]).buffer, "tiny.png");
    expect(result.valid).toBe(false);
    expect(result.error).toContain("corrupted");
    expect(result.error).toContain("too small");
  });

  it("rejects unrecognized file format", () => {
    const garbage = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b]);
    const result = validateFileData(garbage.buffer, "fake.png");
    expect(result.valid).toBe(false);
    expect(result.error).toContain("not a recognized file format");
  });

  it("includes file name in all error messages", () => {
    const garbage = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b]);
    const result = validateFileData(garbage.buffer, "my_photo.png");
    expect(result.error).toContain('"my_photo.png"');
  });
});

describe("validateFileContent", () => {
  it("accepts file with valid PNG content", async () => {
    const file = createFileWithContent("photo.png", PNG_HEADER, "image/png");
    const result = await validateFileContent(file);
    expect(result).toEqual({ valid: true });
  });

  it("rejects file with invalid content", async () => {
    const garbage = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b]);
    const file = createFileWithContent("fake.png", garbage, "image/png");
    const result = await validateFileContent(file);
    expect(result.valid).toBe(false);
  });

  it("handles file read errors gracefully", async () => {
    const file = createFileWithContent("broken.png", PNG_HEADER, "image/png");
    vi.spyOn(file, "slice").mockImplementation(() => {
      throw new Error("read error");
    });
    const result = await validateFileContent(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain("could not be validated");
  });
});

describe("processAndValidateFiles", () => {
  it("returns valid files that pass all checks", async () => {
    const file = createFileWithContent("photo.png", PNG_HEADER, "image/png");
    const result = await processAndValidateFiles([file]);
    expect(result.validFiles).toHaveLength(1);
    expect(result.errors).toHaveLength(0);
  });

  it("filters out files that fail metadata validation", async () => {
    const validFile = createFileWithContent("good.png", PNG_HEADER, "image/png");
    const invalidFile = createFile("bad.txt", 100, "text/plain");
    const result = await processAndValidateFiles([validFile, invalidFile]);
    expect(result.validFiles).toHaveLength(1);
    expect(result.validFiles[0].name).toBe("good.png");
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0]).toContain('"bad.txt"');
  });

  it("filters out files that fail content validation", async () => {
    const garbage = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b]);
    const fakeImage = createFileWithContent("fake.png", garbage, "image/png");
    const result = await processAndValidateFiles([fakeImage]);
    expect(result.validFiles).toHaveLength(0);
    expect(result.errors).toHaveLength(1);
  });

  it("handles empty file list", async () => {
    const result = await processAndValidateFiles([]);
    expect(result.validFiles).toHaveLength(0);
    expect(result.errors).toHaveLength(0);
  });

  it("collects errors from both metadata and content validation", async () => {
    const tooLarge = createFile("huge.png", 21 * 1024 * 1024, "image/png");
    const garbage = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b]);
    const fakeImage = createFileWithContent("fake.jpg", garbage, "image/jpeg");
    const result = await processAndValidateFiles([tooLarge, fakeImage]);
    expect(result.validFiles).toHaveLength(0);
    expect(result.errors).toHaveLength(2);
  });
});

describe("saveFiles", () => {
  it("saves files using window.sculptor.saveFile", async () => {
    const mockSaveFile = vi.fn().mockResolvedValue("/path/to/saved.png");
    window.sculptor = { saveFile: mockSaveFile } as unknown as typeof window.sculptor;

    const file = createFileWithContent("photo.png", PNG_HEADER, "image/png");
    const result = await saveFiles([file]);

    expect(result).toEqual(["/path/to/saved.png"]);
    expect(mockSaveFile).toHaveBeenCalledTimes(1);
  });

  it("filters out failed saves", async () => {
    const mockSaveFile = vi
      .fn()
      .mockResolvedValueOnce("/path/to/first.png")
      .mockRejectedValueOnce(new Error("save failed"))
      .mockResolvedValueOnce("/path/to/third.png");
    window.sculptor = { saveFile: mockSaveFile } as unknown as typeof window.sculptor;

    const files = [
      createFileWithContent("first.png", PNG_HEADER, "image/png"),
      createFileWithContent("second.png", PNG_HEADER, "image/png"),
      createFileWithContent("third.png", PNG_HEADER, "image/png"),
    ];
    const result = await saveFiles(files);

    expect(result).toEqual(["/path/to/first.png", "/path/to/third.png"]);
  });

  it("returns empty array when window.sculptor is not available", async () => {
    delete (window as unknown as Record<string, unknown>).sculptor;

    const file = createFileWithContent("photo.png", PNG_HEADER, "image/png");
    const result = await saveFiles([file]);

    expect(result).toEqual([]);
  });
});

describe("saveFiles (http mode)", () => {
  // In the web/OpenHost build there is no window.sculptor; capabilities are
  // REMOTE so uploads go over HTTP to the backend instead of Electron IPC.
  beforeEach(() => {
    initBackendCapabilities(true);
  });

  afterEach(() => {
    // Restore the default (electron-ipc) capabilities for the rest of the suite.
    initBackendCapabilities(false);
  });

  it("uploads files over HTTP and returns the backend file ids", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async (): Promise<{ fileId: string }> => ({ fileId: "abc123.png" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = createFileWithContent("photo.png", PNG_HEADER, "image/png");
    const result = await saveFiles([file]);

    expect(result).toEqual(["abc123.png"]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${TEST_BASE_URL}/api/v1/upload-file`);
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("does not call window.sculptor.saveFile in http mode", async () => {
    const mockSaveFile = vi.fn();
    window.sculptor = { saveFile: mockSaveFile } as unknown as typeof window.sculptor;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async (): Promise<{ fileId: string }> => ({ fileId: "abc123.png" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = createFileWithContent("photo.png", PNG_HEADER, "image/png");
    await saveFiles([file]);

    expect(mockSaveFile).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("filters out uploads that the backend rejects", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async (): Promise<{ fileId: string }> => ({ fileId: "first.png" }) })
      .mockResolvedValueOnce({ ok: false, status: 413 })
      .mockResolvedValueOnce({ ok: true, json: async (): Promise<{ fileId: string }> => ({ fileId: "third.png" }) });
    vi.stubGlobal("fetch", fetchMock);

    const files = [
      createFileWithContent("first.png", PNG_HEADER, "image/png"),
      createFileWithContent("second.png", PNG_HEADER, "image/png"),
      createFileWithContent("third.png", PNG_HEADER, "image/png"),
    ];
    const result = await saveFiles(files);

    expect(result).toEqual(["first.png", "third.png"]);
  });

  it("filters out uploads that throw a network error", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    const file = createFileWithContent("photo.png", PNG_HEADER, "image/png");
    const result = await saveFiles([file]);

    expect(result).toEqual([]);
  });
});

describe("exported constants", () => {
  it("exports expected allowed extensions", () => {
    expect(ALLOWED_EXTENSIONS).toContain(".png");
    expect(ALLOWED_EXTENSIONS).toContain(".jpg");
    expect(ALLOWED_EXTENSIONS).toContain(".jpeg");
    expect(ALLOWED_EXTENSIONS).toContain(".webp");
    expect(ALLOWED_EXTENSIONS).toContain(".gif");
    expect(ALLOWED_EXTENSIONS).not.toContain(".pdf");
  });

  it("exports expected allowed MIME types", () => {
    expect(ALLOWED_MIME_TYPES).toContain("image/png");
    expect(ALLOWED_MIME_TYPES).toContain("image/jpeg");
    expect(ALLOWED_MIME_TYPES).toContain("image/webp");
    expect(ALLOWED_MIME_TYPES).toContain("image/gif");
    expect(ALLOWED_MIME_TYPES).not.toContain("application/pdf");
  });
});
