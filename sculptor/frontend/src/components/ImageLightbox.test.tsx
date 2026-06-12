import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImageLightbox } from "./ImageLightbox";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

type ImageLightboxProps = React.ComponentProps<typeof ImageLightbox>;

const singleImage = [{ url: "data:image/png;base64,AAA", name: "photo.png", isVideo: false }];

const multipleImages = [
  { url: "data:image/png;base64,AAA", name: "first.png", isVideo: false },
  { url: "data:image/png;base64,BBB", name: "second.jpg", isVideo: false },
  { url: "data:image/png;base64,CCC", name: "third.webp", isVideo: false },
];

const renderLightbox = (props: Partial<ImageLightboxProps> = {}): RenderResult => {
  const defaultProps: ImageLightboxProps = {
    media: singleImage,
    initialIndex: 0,
    onClose: vi.fn(),
    ...props,
  };
  return render(<ImageLightbox {...defaultProps} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ImageLightbox", () => {
  describe("single image", () => {
    it("renders the image with correct src and alt text", () => {
      renderLightbox();
      const img = screen.getByAltText("Full size: photo.png");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", "data:image/png;base64,AAA");
    });

    it("renders the file name", () => {
      renderLightbox();
      expect(screen.getByText("photo.png")).toBeInTheDocument();
    });

    it("does not show image counter for single image", () => {
      renderLightbox();
      expect(screen.queryByText(/\d+\/\d+/)).not.toBeInTheDocument();
    });

    it("renders with correct aria-label", () => {
      renderLightbox();
      expect(screen.getByLabelText("Image preview: photo.png")).toBeInTheDocument();
    });

    it("does not render navigation arrows for single image", () => {
      renderLightbox();
      expect(screen.queryByLabelText("Previous image")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Next image")).not.toBeInTheDocument();
    });
  });

  describe("multiple images", () => {
    it("shows the image at the initial index", () => {
      renderLightbox({ media: multipleImages, initialIndex: 1 });
      expect(screen.getByAltText("Full size: second.jpg")).toBeInTheDocument();
    });

    it("shows image counter with correct format", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.getByText(/first\.png/)).toHaveTextContent("first.png (1/3)");
    });

    it("shows correct counter for middle image", () => {
      renderLightbox({ media: multipleImages, initialIndex: 1 });
      expect(screen.getByText(/second\.jpg/)).toHaveTextContent("second.jpg (2/3)");
    });

    it("renders only next arrow at start", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.queryByLabelText("Previous image")).not.toBeInTheDocument();
      expect(screen.getByLabelText("Next image")).toBeInTheDocument();
    });

    it("renders both arrows in the middle", () => {
      renderLightbox({ media: multipleImages, initialIndex: 1 });
      expect(screen.getByLabelText("Previous image")).toBeInTheDocument();
      expect(screen.getByLabelText("Next image")).toBeInTheDocument();
    });

    it("renders only previous arrow at end", () => {
      renderLightbox({ media: multipleImages, initialIndex: 2 });
      expect(screen.getByLabelText("Previous image")).toBeInTheDocument();
      expect(screen.queryByLabelText("Next image")).not.toBeInTheDocument();
    });
  });

  describe("navigation arrow buttons", () => {
    it("navigates to next image when clicking next arrow", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();

      fireEvent.click(screen.getByLabelText("Next image"));

      expect(screen.getByAltText("Full size: second.jpg")).toBeInTheDocument();
      expect(screen.queryByAltText("Full size: first.png")).not.toBeInTheDocument();
    });

    it("navigates to previous image when clicking previous arrow", () => {
      renderLightbox({ media: multipleImages, initialIndex: 1 });
      expect(screen.getByAltText("Full size: second.jpg")).toBeInTheDocument();

      fireEvent.click(screen.getByLabelText("Previous image"));

      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();
    });

    it("stays on last image when at end (no wrap)", () => {
      renderLightbox({ media: multipleImages, initialIndex: 2 });
      expect(screen.getByAltText("Full size: third.webp")).toBeInTheDocument();

      // Next arrow is hidden at end, so image stays the same
      expect(screen.queryByLabelText("Next image")).not.toBeInTheDocument();
      expect(screen.getByAltText("Full size: third.webp")).toBeInTheDocument();
    });

    it("stays on first image when at start (no wrap)", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();

      // Previous arrow is hidden at start, so image stays the same
      expect(screen.queryByLabelText("Previous image")).not.toBeInTheDocument();
      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();
    });

    it("updates counter after clicking navigation arrows", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.getByText(/first\.png/)).toHaveTextContent("first.png (1/3)");

      fireEvent.click(screen.getByLabelText("Next image"));

      expect(screen.getByText(/second\.jpg/)).toHaveTextContent("second.jpg (2/3)");
    });
  });

  describe("keyboard navigation", () => {
    it("navigates to next image with ArrowRight", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();

      fireEvent.keyDown(window, { key: "ArrowRight" });

      expect(screen.getByAltText("Full size: second.jpg")).toBeInTheDocument();
      expect(screen.queryByAltText("Full size: first.png")).not.toBeInTheDocument();
    });

    it("navigates to previous image with ArrowLeft", () => {
      renderLightbox({ media: multipleImages, initialIndex: 1 });
      expect(screen.getByAltText("Full size: second.jpg")).toBeInTheDocument();

      fireEvent.keyDown(window, { key: "ArrowLeft" });

      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();
    });

    it("stays on last image with ArrowRight at end (no wrap)", () => {
      renderLightbox({ media: multipleImages, initialIndex: 2 });
      expect(screen.getByAltText("Full size: third.webp")).toBeInTheDocument();

      fireEvent.keyDown(window, { key: "ArrowRight" });

      expect(screen.getByAltText("Full size: third.webp")).toBeInTheDocument();
    });

    it("stays on first image with ArrowLeft at start (no wrap)", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();

      fireEvent.keyDown(window, { key: "ArrowLeft" });

      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();
    });

    it("does not respond to arrow keys for single image", () => {
      renderLightbox({ media: singleImage, initialIndex: 0 });
      expect(screen.getByAltText("Full size: photo.png")).toBeInTheDocument();

      fireEvent.keyDown(window, { key: "ArrowRight" });

      // Still showing same image
      expect(screen.getByAltText("Full size: photo.png")).toBeInTheDocument();
    });

    it("updates counter after keyboard navigation", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });
      expect(screen.getByText(/first\.png/)).toHaveTextContent("first.png (1/3)");

      fireEvent.keyDown(window, { key: "ArrowRight" });

      expect(screen.getByText(/second\.jpg/)).toHaveTextContent("second.jpg (2/3)");
    });

    it("ignores non-arrow keys", () => {
      renderLightbox({ media: multipleImages, initialIndex: 0 });

      fireEvent.keyDown(window, { key: "a" });
      fireEvent.keyDown(window, { key: "Enter" });
      fireEvent.keyDown(window, { key: "Space" });

      expect(screen.getByAltText("Full size: first.png")).toBeInTheDocument();
    });
  });

  describe("video support", () => {
    const videoMedia = [{ url: "data:video/mp4;base64,AAA", name: "recording.mp4", isVideo: true }];

    it("renders a video element for video files", () => {
      renderLightbox({ media: videoMedia, initialIndex: 0 });
      const video = document.querySelector("video");
      expect(video).toBeInTheDocument();
      expect(video).toHaveAttribute("src", "data:video/mp4;base64,AAA");
      expect(video).toHaveAttribute("controls");
    });

    it("renders with correct aria-label for videos", () => {
      renderLightbox({ media: videoMedia, initialIndex: 0 });
      expect(screen.getByLabelText("Video preview: recording.mp4")).toBeInTheDocument();
    });
  });

  describe("close behavior", () => {
    it("calls onClose when dialog is closed", () => {
      const onClose = vi.fn();
      renderLightbox({ onClose });

      // Radix Dialog calls onOpenChange(false) when Escape is pressed
      // We test via the Escape key which Radix Dialog handles
      fireEvent.keyDown(document, { key: "Escape" });

      expect(onClose).toHaveBeenCalled();
    });
  });
});
