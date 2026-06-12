import { Flex } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { FilePreview } from "~/components/FilePreview";

// Placeholder images at various aspect ratios via picsum
const LANDSCAPE_URL = "https://picsum.photos/seed/landscape/800/500";
const PORTRAIT_URL = "https://picsum.photos/seed/portrait/400/700";
const SQUARE_URL = "https://picsum.photos/seed/square/600/600";
const WIDE_URL = "https://picsum.photos/seed/wide/1200/400";
const TALL_URL = "https://picsum.photos/seed/tall/300/900";

const noop = (): void => {};

const handleClick = (): void => {
  console.log("Thumbnail clicked — would open lightbox");
};

/**
 * Renders FilePreview thumbnails in the same horizontal Flex layout
 * that FilePreviewList uses in inline mode, so we can visualise the
 * thumbnail strip without needing a running backend.
 */
const InlineStrip = ({ files }: { files: Array<{ url: string; name: string }> }): ReactElement => (
  <div style={{ maxWidth: "500px", background: "var(--accent-3)", borderRadius: "var(--radius-3)", padding: "12px" }}>
    <p style={{ margin: "0 0 8px", fontSize: "14px" }}>This is a user message with some attached images below.</p>
    <Flex direction="row" gap="1" wrap="nowrap" style={{ overflowX: "auto", padding: "4px 0" }}>
      {files.map((f) => (
        <FilePreview
          key={f.name}
          filePath={`/uploads/${f.name}`}
          fileUrl={f.url}
          isFailed={false}
          isPdf={false}
          isVideo={false}
          fileName={f.name}
          displayMode="inline"
          onError={noop}
          onClick={handleClick}
        />
      ))}
    </Flex>
  </div>
);

const meta = {
  title: "Custom/FilePreviewStrip",
  component: InlineStrip,
} satisfies Meta<typeof InlineStrip>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const SingleImage: Story = {
  args: {
    files: [{ url: LANDSCAPE_URL, name: "screenshot.png" }],
  },
};

export const TwoImages: Story = {
  args: {
    files: [
      { url: LANDSCAPE_URL, name: "screenshot-1.png" },
      { url: PORTRAIT_URL, name: "screenshot-2.png" },
    ],
  },
};

export const ThreeImages: Story = {
  args: {
    files: [
      { url: LANDSCAPE_URL, name: "overview.png" },
      { url: SQUARE_URL, name: "detail.png" },
      { url: WIDE_URL, name: "banner.png" },
    ],
  },
};

export const ManyImages: Story = {
  args: {
    files: [
      { url: LANDSCAPE_URL, name: "img-1.png" },
      { url: PORTRAIT_URL, name: "img-2.png" },
      { url: SQUARE_URL, name: "img-3.png" },
      { url: WIDE_URL, name: "img-4.png" },
      { url: TALL_URL, name: "img-5.png" },
    ],
  },
};

export const MixedAspectRatios: Story = {
  args: {
    files: [
      { url: WIDE_URL, name: "panorama.png" },
      { url: TALL_URL, name: "mobile-screenshot.png" },
      { url: SQUARE_URL, name: "avatar.png" },
    ],
  },
};

export const FailedLoad: Story = {
  args: { files: [] },
  render: (): ReactElement => (
    <div style={{ maxWidth: "500px", background: "var(--accent-3)", borderRadius: "var(--radius-3)", padding: "12px" }}>
      <p style={{ margin: "0 0 8px", fontSize: "14px" }}>Message with a failed image.</p>
      <Flex direction="row" gap="1" wrap="nowrap" style={{ overflowX: "auto", padding: "4px 0" }}>
        <FilePreview
          filePath="/uploads/good.png"
          fileUrl={LANDSCAPE_URL}
          isFailed={false}
          isPdf={false}
          isVideo={false}
          fileName="good.png"
          displayMode="inline"
          onError={noop}
          onClick={handleClick}
        />
        <FilePreview
          filePath="/uploads/broken.png"
          isFailed={true}
          isPdf={false}
          isVideo={false}
          fileName="broken.png"
          displayMode="inline"
          onError={noop}
        />
      </Flex>
    </div>
  ),
};

export const Loading: Story = {
  args: { files: [] },
  render: (): ReactElement => (
    <div style={{ maxWidth: "500px", background: "var(--accent-3)", borderRadius: "var(--radius-3)", padding: "12px" }}>
      <p style={{ margin: "0 0 8px", fontSize: "14px" }}>Message with images still loading.</p>
      <Flex direction="row" gap="1" wrap="nowrap" style={{ overflowX: "auto", padding: "4px 0" }}>
        <FilePreview
          filePath="/uploads/loading-1.png"
          isFailed={false}
          isPdf={false}
          isVideo={false}
          fileName="loading-1.png"
          displayMode="inline"
          onError={noop}
        />
        <FilePreview
          filePath="/uploads/loading-2.png"
          isFailed={false}
          isPdf={false}
          isVideo={false}
          fileName="loading-2.png"
          displayMode="inline"
          onError={noop}
        />
      </Flex>
    </div>
  ),
};
