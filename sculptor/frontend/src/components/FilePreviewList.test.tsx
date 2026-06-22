import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { initBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";

import { FilePreviewList } from "./FilePreviewList";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

type FilePreviewListProps = React.ComponentProps<typeof FilePreviewList>;

const renderList = (props: Partial<FilePreviewListProps> = {}): RenderResult => {
  const defaultProps: FilePreviewListProps = {
    files: [],
    ...props,
  };
  return render(<FilePreviewList {...defaultProps} />, { wrapper: Wrapper });
};

const mockGetFileData = vi.fn();

beforeEach(() => {
  window.sculptor = {
    getFileData: mockGetFileData,
  } as unknown as typeof window.sculptor;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  // Reset back to the default (electron-ipc) capabilities; the http-mode tests
  // below flip this to REMOTE.
  initBackendCapabilities(false);
  delete (window as unknown as Record<string, unknown>).sculptor;
});

describe("FilePreviewList", () => {
  describe("empty state", () => {
    it("does not render the file preview list when files array is empty", () => {
      renderList({ files: [] });
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW_LIST)).not.toBeInTheDocument();
    });
  });

  describe("rendering files", () => {
    it("renders a FilePreview for each file", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png", "/tmp/b.jpg"] });

      await waitFor(() => {
        const previews = screen.getAllByTestId(ElementIds.FILE_PREVIEW_CONTAINER);
        expect(previews).toHaveLength(2);
      });
    });

    it("renders the file preview list container", () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png"] });
      expect(screen.getByTestId(ElementIds.FILE_PREVIEW_LIST)).toBeInTheDocument();
    });

    it("loads file data via window.sculptor.getFileData", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png"] });

      await waitFor(() => {
        expect(mockGetFileData).toHaveBeenCalledWith("/tmp/a.png");
      });
    });
  });

  describe("file loading", () => {
    it("displays image after file data loads", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,LOADED");
      renderList({ files: ["/tmp/photo.png"] });

      await waitFor(() => {
        const img = screen.getByAltText("Attachment: photo.png");
        expect(img).toHaveAttribute("src", "data:image/png;base64,LOADED");
      });
    });

    it("marks file as failed when getFileData rejects", async () => {
      mockGetFileData.mockRejectedValue(new Error("load error"));
      renderList({ files: ["/tmp/broken.png"] });

      // The FilePreview should be rendered in failed state (no img element)
      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER)).toBeInTheDocument();
        expect(screen.queryByAltText("Attachment: broken.png")).not.toBeInTheDocument();
      });
    });
  });

  describe("file removal", () => {
    it("calls onRemoveFile with the file path when remove button is clicked", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      const onRemoveFile = vi.fn();
      renderList({ files: ["/tmp/photo.png"], onRemoveFile });

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.FILE_PREVIEW_REMOVE)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId(ElementIds.FILE_PREVIEW_REMOVE));
      expect(onRemoveFile).toHaveBeenCalledWith("/tmp/photo.png");
    });

    it("does not render remove buttons when onRemoveFile is not provided", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/photo.png"] });

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER)).toBeInTheDocument();
      });

      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW_REMOVE)).not.toBeInTheDocument();
    });
  });

  describe("incremental loading", () => {
    it("only loads newly added files on re-render", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");

      const { rerender } = render(<FilePreviewList files={["/tmp/a.png"]} />, { wrapper: Wrapper });

      await waitFor(() => {
        expect(mockGetFileData).toHaveBeenCalledWith("/tmp/a.png");
      });

      mockGetFileData.mockClear();

      // rerender must use the wrapper param (not inline Theme) to avoid remounting
      rerender(<FilePreviewList files={["/tmp/a.png", "/tmp/b.png"]} />);

      await waitFor(() => {
        expect(mockGetFileData).toHaveBeenCalledWith("/tmp/b.png");
      });

      // Should NOT reload the first file
      expect(mockGetFileData).not.toHaveBeenCalledWith("/tmp/a.png");
    });
  });

  describe("PDF handling", () => {
    it("renders PDF files with file icon instead of image", async () => {
      mockGetFileData.mockResolvedValue("data:application/pdf;base64,AAA");
      renderList({ files: ["/tmp/doc.pdf"] });

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER)).toBeInTheDocument();
      });

      // PDF previews should NOT have an img element with the preview testid
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW)).not.toBeInTheDocument();
    });
  });

  describe("lightbox", () => {
    it("opens lightbox when clicking an image thumbnail", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,FULL");
      renderList({ files: ["/tmp/photo.png"] });

      await waitFor(() => {
        const img = screen.getByAltText("Attachment: photo.png");
        expect(img).toBeInTheDocument();
      });

      // Click the container to open the lightbox
      const container = screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER);
      const innerContainer = container.querySelector("[class*='previewContainer']");
      fireEvent.click(innerContainer!);

      await waitFor(() => {
        expect(screen.getByAltText("Full size: photo.png")).toBeInTheDocument();
      });
    });

    it("does not open lightbox for PDF files", async () => {
      mockGetFileData.mockResolvedValue("data:application/pdf;base64,AAA");
      renderList({ files: ["/tmp/doc.pdf"] });

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER)).toBeInTheDocument();
      });

      const container = screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER);
      const innerContainer = container.querySelector("[class*='previewContainer']");
      fireEvent.click(innerContainer!);

      // Should NOT show the lightbox
      expect(screen.queryByLabelText(/Image preview/)).not.toBeInTheDocument();
    });

    it("does not open lightbox for failed files", async () => {
      mockGetFileData.mockRejectedValue(new Error("load error"));
      renderList({ files: ["/tmp/broken.png"] });

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER)).toBeInTheDocument();
      });

      const container = screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER);
      const innerContainer = container.querySelector("[class*='previewContainer']");
      fireEvent.click(innerContainer!);

      expect(screen.queryByLabelText(/Image preview/)).not.toBeInTheDocument();
    });

    it("shows keyboard navigation counter for multiple images in lightbox", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,FULL");
      renderList({ files: ["/tmp/a.png", "/tmp/b.png"] });

      await waitFor(() => {
        const imgs = screen.getAllByTestId(ElementIds.FILE_PREVIEW);
        expect(imgs).toHaveLength(2);
      });

      // Click first image to open lightbox
      const containers = screen.getAllByTestId(ElementIds.FILE_PREVIEW_CONTAINER);
      const firstInner = containers[0].querySelector("[class*='previewContainer']");
      fireEvent.click(firstInner!);

      await waitFor(() => {
        expect(screen.getByText(/1\/2/)).toBeInTheDocument();
      });
    });

    it("supports keyboard navigation in lightbox with multiple images", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,FULL");
      renderList({ files: ["/tmp/a.png", "/tmp/b.png"] });

      await waitFor(() => {
        const imgs = screen.getAllByTestId(ElementIds.FILE_PREVIEW);
        expect(imgs).toHaveLength(2);
      });

      // Open lightbox on first image
      const containers = screen.getAllByTestId(ElementIds.FILE_PREVIEW_CONTAINER);
      const firstInner = containers[0].querySelector("[class*='previewContainer']");
      fireEvent.click(firstInner!);

      await waitFor(() => {
        expect(screen.getByAltText("Full size: a.png")).toBeInTheDocument();
      });

      // Navigate to next image
      fireEvent.keyDown(window, { key: "ArrowRight" });

      await waitFor(() => {
        expect(screen.getByAltText("Full size: b.png")).toBeInTheDocument();
      });
    });

    it("closes lightbox and returns to thumbnail view", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,FULL");
      renderList({ files: ["/tmp/photo.png"] });

      await waitFor(() => {
        expect(screen.getByAltText("Attachment: photo.png")).toBeInTheDocument();
      });

      // Open lightbox
      const container = screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER);
      const innerContainer = container.querySelector("[class*='previewContainer']");
      fireEvent.click(innerContainer!);

      await waitFor(() => {
        expect(screen.getByAltText("Full size: photo.png")).toBeInTheDocument();
      });

      // Close via Escape
      fireEvent.keyDown(document, { key: "Escape" });

      await waitFor(() => {
        expect(screen.queryByAltText("Full size: photo.png")).not.toBeInTheDocument();
      });
    });
  });

  describe("inline display mode", () => {
    it("renders images directly without compact thumbnail wrapper in inline mode", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,LOADED");
      renderList({ files: ["/tmp/photo.png"], displayMode: "inline" });

      await waitFor(() => {
        const img = screen.getByAltText("Attachment: photo.png");
        expect(img).toBeInTheDocument();
        expect(img.className).toContain("inlineMedia");
      });
    });

    it("opens lightbox when clicking an inline image", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,FULL");
      renderList({ files: ["/tmp/photo.png"], displayMode: "inline" });

      await waitFor(() => {
        expect(screen.getByAltText("Attachment: photo.png")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByAltText("Attachment: photo.png"));

      await waitFor(() => {
        expect(screen.getByAltText("Full size: photo.png")).toBeInTheDocument();
      });
    });

    it("renders multiple images in inline mode as a horizontal strip", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png", "/tmp/b.png", "/tmp/c.png"], displayMode: "inline" });

      await waitFor(() => {
        const imgs = screen.getAllByTestId(ElementIds.FILE_PREVIEW);
        expect(imgs).toHaveLength(3);
      });

      // All images should use inline styling
      const imgs = screen.getAllByTestId(ElementIds.FILE_PREVIEW);
      for (const img of imgs) {
        expect(img.className).toContain("inlineMedia");
      }
    });

    it("opens lightbox on correct image when clicking second inline image", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,FULL");
      renderList({ files: ["/tmp/a.png", "/tmp/b.png"], displayMode: "inline" });

      await waitFor(() => {
        expect(screen.getAllByTestId(ElementIds.FILE_PREVIEW)).toHaveLength(2);
      });

      // Click second image
      fireEvent.click(screen.getByAltText("Attachment: b.png"));

      await waitFor(() => {
        // Should open lightbox showing image 2/2
        expect(screen.getByText(/2\/2/)).toBeInTheDocument();
      });
    });
  });

  describe("thumbnail strip layout", () => {
    it("enables horizontal scrolling via overflow-x auto", () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png"] });

      const list = screen.getByTestId(ElementIds.FILE_PREVIEW_LIST);
      expect(list).toHaveStyle({ overflowX: "auto" });
    });

    it("enables horizontal scrolling in inline mode", () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png"], displayMode: "inline" });

      const list = screen.getByTestId(ElementIds.FILE_PREVIEW_LIST);
      expect(list).toHaveStyle({ overflowX: "auto" });
    });

    it("applies compact padding when displayMode is compact", () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png"] });

      const list = screen.getByTestId(ElementIds.FILE_PREVIEW_LIST);
      expect(list).toHaveStyle({ padding: "8px 8px 4px" });
    });

    it("applies inline padding when displayMode is inline", () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/tmp/a.png"], displayMode: "inline" });

      const list = screen.getByTestId(ElementIds.FILE_PREVIEW_LIST);
      expect(list).toHaveStyle({ padding: "4px 0" });
    });
  });

  describe("file name extraction", () => {
    it("extracts file name from Unix-style path", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["/home/user/photos/vacation.png"] });

      await waitFor(() => {
        expect(screen.getByAltText("Attachment: vacation.png")).toBeInTheDocument();
      });
    });

    it("extracts file name from Windows-style path", async () => {
      mockGetFileData.mockResolvedValue("data:image/png;base64,AAA");
      renderList({ files: ["C:\\Users\\photos\\vacation.png"] });

      await waitFor(() => {
        expect(screen.getByAltText("Attachment: vacation.png")).toBeInTheDocument();
      });
    });
  });

  describe("http mode (remote backend)", () => {
    // In the web/OpenHost build there is no window.sculptor; capabilities are
    // REMOTE so previews are fetched over HTTP from the backend instead of
    // through Electron IPC.
    beforeEach(() => {
      initBackendCapabilities(true);
      // The shared mockGetFileData accumulates calls across this file's tests
      // (vitest does not auto-clear vi.fn() call history), so clear it here to
      // keep "the Electron IPC path must not be used in http mode" accurate.
      mockGetFileData.mockClear();
      // jsdom does not implement URL.createObjectURL; stub it so the http path
      // can turn the fetched blob into an <img> src.
      (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => "blob:mock-url");
    });

    afterEach(() => {
      delete (URL as unknown as Record<string, unknown>).createObjectURL;
    });

    it("loads previews over HTTP from the uploaded-file endpoint", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        blob: async (): Promise<Blob> => new Blob(["png-bytes"], { type: "image/png" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      renderList({ files: ["abc123.png"] });

      await waitFor(() => {
        const img = screen.getByAltText("Attachment: abc123.png");
        expect(img).toHaveAttribute("src", "blob:mock-url");
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url] = fetchMock.mock.calls[0] as [string];
      expect(url).toContain("/api/v1/uploaded-file/abc123.png");
      // The Electron IPC path must not be used in http mode.
      expect(mockGetFileData).not.toHaveBeenCalled();
    });

    it("marks the file as failed when the HTTP request is not ok", async () => {
      const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 404 });
      vi.stubGlobal("fetch", fetchMock);

      renderList({ files: ["missing.png"] });

      await waitFor(() => {
        expect(screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER)).toBeInTheDocument();
        expect(screen.queryByAltText("Attachment: missing.png")).not.toBeInTheDocument();
      });
    });
  });
});
