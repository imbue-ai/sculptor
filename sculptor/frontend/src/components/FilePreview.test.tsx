import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { FilePreview } from "./FilePreview";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

type FilePreviewProps = React.ComponentProps<typeof FilePreview>;

const defaultProps: FilePreviewProps = {
  filePath: "/tmp/test/photo.png",
  fileUrl: "data:image/png;base64,ABC",
  isFailed: false,
  isPdf: false,
  isVideo: false,
  fileName: "photo.png",
  onRemove: vi.fn(),
  onError: vi.fn(),
  onClick: vi.fn(),
};

const renderPreview = (props: Partial<FilePreviewProps> = {}): RenderResult => {
  return render(<FilePreview {...defaultProps} {...props} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("FilePreview", () => {
  describe("image rendering", () => {
    it("renders an image thumbnail when fileUrl is provided", () => {
      renderPreview();
      const img = screen.getByAltText("Attachment: photo.png");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", "data:image/png;base64,ABC");
    });

    it("renders the correct data-testid on the image element", () => {
      renderPreview();
      expect(screen.getByTestId(ElementIds.FILE_PREVIEW)).toBeInTheDocument();
    });

    it("renders the correct data-path attribute for image identification", () => {
      renderPreview();
      const img = screen.getByTestId(ElementIds.FILE_PREVIEW);
      expect(img).toHaveAttribute("data-path", "/tmp/test/photo.png");
    });

    it("renders the container with the correct data-testid", () => {
      renderPreview();
      expect(screen.getByTestId(ElementIds.FILE_PREVIEW_CONTAINER)).toBeInTheDocument();
    });
  });

  describe("loading state", () => {
    it("renders a loading skeleton (not the error icon) in compact mode while fileUrl is undefined", () => {
      const { container } = renderPreview({ fileUrl: undefined, isFailed: false });
      expect(container.querySelector(".previewSkeleton")).toBeInTheDocument();
      // The failed/error placeholder must NOT appear while still loading.
      expect(container.querySelector(".previewError")).not.toBeInTheDocument();
      expect(screen.queryByAltText("Attachment: photo.png")).not.toBeInTheDocument();
    });
  });

  describe("error state", () => {
    it("renders error icon when isFailed is true", () => {
      renderPreview({ isFailed: true });
      expect(screen.queryByAltText("Attachment: photo.png")).not.toBeInTheDocument();
    });

    it("calls onError when image fails to load", () => {
      const onError = vi.fn();
      renderPreview({ onError });
      const img = screen.getByAltText("Attachment: photo.png");
      fireEvent.error(img);
      expect(onError).toHaveBeenCalledTimes(1);
    });
  });

  describe("PDF state", () => {
    it("renders file icon for PDF files", () => {
      renderPreview({ isPdf: true });
      expect(screen.queryByAltText("Attachment: photo.png")).not.toBeInTheDocument();
    });
  });

  describe("remove button", () => {
    it("renders remove button when onRemove is provided", () => {
      renderPreview({ onRemove: vi.fn() });
      expect(screen.getByTestId(ElementIds.FILE_PREVIEW_REMOVE)).toBeInTheDocument();
    });

    it("does not render remove button when onRemove is not provided", () => {
      renderPreview({ onRemove: undefined });
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW_REMOVE)).not.toBeInTheDocument();
    });

    it("calls onRemove when remove button is clicked", () => {
      const onRemove = vi.fn();
      renderPreview({ onRemove });
      fireEvent.click(screen.getByTestId(ElementIds.FILE_PREVIEW_REMOVE));
      expect(onRemove).toHaveBeenCalledTimes(1);
    });

    it("stops event propagation when remove button is clicked", () => {
      const onClick = vi.fn();
      const onRemove = vi.fn();
      renderPreview({ onClick, onRemove });
      fireEvent.click(screen.getByTestId(ElementIds.FILE_PREVIEW_REMOVE));
      expect(onRemove).toHaveBeenCalledTimes(1);
      // onClick should NOT be called because stopPropagation is used
      expect(onClick).not.toHaveBeenCalled();
    });
  });

  describe("click behavior", () => {
    it("calls onClick when the image container is clicked", () => {
      const onClick = vi.fn();
      const { container } = renderPreview({ onClick });
      const innerContainer = container.querySelector(".previewContainer");
      fireEvent.click(innerContainer!);
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("does not call onClick when isFailed is true", () => {
      const onClick = vi.fn();
      const { container } = renderPreview({ onClick, isFailed: true });
      const innerContainer = container.querySelector(".previewContainerFailed");
      fireEvent.click(innerContainer!);
      expect(onClick).not.toHaveBeenCalled();
    });

    it("does not call onClick when isPdf is true", () => {
      const onClick = vi.fn();
      const { container } = renderPreview({ onClick, isPdf: true });
      const innerContainer = container.querySelector(".previewContainer");
      fireEvent.click(innerContainer!);
      expect(onClick).not.toHaveBeenCalled();
    });

    it("does not apply clickable class when onClick is not provided", () => {
      const { container } = renderPreview({ onClick: undefined });
      const innerContainer = container.querySelector(".previewContainer");
      expect(innerContainer).not.toHaveClass("clickable");
    });
  });

  describe("failed container styling", () => {
    it("uses previewContainerFailed class when isFailed is true", () => {
      const { container } = renderPreview({ isFailed: true });
      expect(container.querySelector(".previewContainerFailed")).toBeInTheDocument();
      expect(container.querySelector(".previewContainer")).not.toBeInTheDocument();
    });

    it("uses previewContainer class when isFailed is false", () => {
      const { container } = renderPreview({ isFailed: false });
      expect(container.querySelector(".previewContainer")).toBeInTheDocument();
      expect(container.querySelector(".previewContainerFailed")).not.toBeInTheDocument();
    });
  });
});

describe("FilePreview inline mode", () => {
  describe("image rendering", () => {
    it("renders the image with inline styles when displayMode is inline", () => {
      const { container } = renderPreview({ displayMode: "inline" });
      const img = screen.getByAltText("Attachment: photo.png");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", "data:image/png;base64,ABC");
      expect(container.querySelector(".inlineWrapper")).toBeInTheDocument();
      expect(container.querySelector(".previewWrapper")).not.toBeInTheDocument();
    });

    it("applies the inlineMedia class to the image element", () => {
      renderPreview({ displayMode: "inline" });
      const img = screen.getByTestId(ElementIds.FILE_PREVIEW);
      expect(img.className).toContain("inlineMedia");
    });

    it("calls onClick when the image is clicked", () => {
      const onClick = vi.fn();
      renderPreview({ displayMode: "inline", onClick });
      const img = screen.getByAltText("Attachment: photo.png");
      fireEvent.click(img);
      expect(onClick).toHaveBeenCalledTimes(1);
    });
  });

  describe("video rendering", () => {
    it("renders a video element with controls in inline mode", () => {
      renderPreview({ displayMode: "inline", isVideo: true });
      const video = screen.getByTestId(ElementIds.FILE_PREVIEW);
      expect(video.tagName).toBe("VIDEO");
      expect(video).toHaveAttribute("controls");
      expect(video).toHaveAttribute("src", "data:image/png;base64,ABC");
    });
  });

  describe("loading state", () => {
    it("renders a skeleton placeholder when fileUrl is undefined in inline mode", () => {
      const { container } = renderPreview({ displayMode: "inline", fileUrl: undefined });
      expect(container.querySelector(".inlineSkeleton")).toBeInTheDocument();
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW)).not.toBeInTheDocument();
    });
  });

  describe("failed state", () => {
    it("renders an inline error when isFailed is true", () => {
      renderPreview({ displayMode: "inline", isFailed: true });
      expect(screen.queryByAltText("Attachment: photo.png")).not.toBeInTheDocument();
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW)).not.toBeInTheDocument();
    });

    it("renders error state with inlineError class for styled error card", () => {
      const { container } = renderPreview({ displayMode: "inline", isFailed: true });
      expect(container.querySelector(".inlineError")).toBeInTheDocument();
    });

    it("displays the filename in the inline error state", () => {
      renderPreview({ displayMode: "inline", isFailed: true });
      expect(screen.getByText("photo.png")).toBeInTheDocument();
    });
  });

  describe("PDF fallback", () => {
    it("renders a file icon instead of an image for PDF files in inline mode", () => {
      renderPreview({ displayMode: "inline", isPdf: true });
      // No img or video element should be rendered
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW)).not.toBeInTheDocument();
      expect(screen.queryByAltText("Attachment: photo.png")).not.toBeInTheDocument();
    });
  });

  describe("clickable state", () => {
    it("applies clickable class when onClick is provided in inline mode", () => {
      const onClick = vi.fn();
      renderPreview({ displayMode: "inline", onClick });
      const img = screen.getByTestId(ElementIds.FILE_PREVIEW);
      expect(img.className).toContain("clickable");
    });

    it("does not apply clickable class when onClick is not provided in inline mode", () => {
      renderPreview({ displayMode: "inline", onClick: undefined });
      const img = screen.getByTestId(ElementIds.FILE_PREVIEW);
      expect(img.className).not.toContain("clickable");
    });
  });

  describe("copy image context menu", () => {
    it("shows Copy Image on right-click when allowCopyImage is set", async () => {
      renderPreview({ displayMode: "inline", allowCopyImage: true });
      fireEvent.contextMenu(screen.getByTestId(ElementIds.FILE_PREVIEW));
      expect(await screen.findByTestId(ElementIds.FILE_PREVIEW_COPY_IMAGE)).toBeInTheDocument();
    });

    it("does not show Copy Image when allowCopyImage is not set", () => {
      renderPreview({ displayMode: "inline" });
      fireEvent.contextMenu(screen.getByTestId(ElementIds.FILE_PREVIEW));
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW_COPY_IMAGE)).not.toBeInTheDocument();
    });

    it("does not show Copy Image for videos even when allowCopyImage is set", () => {
      renderPreview({ displayMode: "inline", isVideo: true, allowCopyImage: true });
      fireEvent.contextMenu(screen.getByTestId(ElementIds.FILE_PREVIEW));
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW_COPY_IMAGE)).not.toBeInTheDocument();
    });
  });

  describe("container", () => {
    it("uses inlineWrapper class instead of previewWrapper", () => {
      const { container } = renderPreview({ displayMode: "inline" });
      expect(container.querySelector(".inlineWrapper")).toBeInTheDocument();
      expect(container.querySelector(".previewWrapper")).not.toBeInTheDocument();
    });

    it("does not render remove button in inline mode", () => {
      renderPreview({ displayMode: "inline", onRemove: vi.fn() });
      expect(screen.queryByTestId(ElementIds.FILE_PREVIEW_REMOVE)).not.toBeInTheDocument();
    });
  });
});
