// The `--mobile-*` tokens live behind the `.mobileTheme` class; the app loads
// this in Main.tsx, but Storybook only pulls in index.css, so import it here.
import "~/styles/mobile-theme.css";

import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { MobileChatSkeleton } from "~/pages/workspace/mobile/MobileChatSkeleton";

/**
 * Renders the mobile chat loading skeleton inside a phone-width, `--mobile-surface-2`
 * column of fixed height, so the flex-filled bubble transcript can be eyeballed
 * the way it appears in the workspace shell's chat area on a cold load (the
 * window in which the chat panel would otherwise sit blank).
 */
const Wrapper = (): ReactElement => (
  <div
    className="mobileTheme"
    style={{
      background: "var(--mobile-surface-2)",
      display: "flex",
      flexDirection: "column",
      width: "390px",
      height: "600px",
    }}
  >
    <MobileChatSkeleton />
  </div>
);

const meta = {
  title: "Custom/MobileChatSkeleton",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
