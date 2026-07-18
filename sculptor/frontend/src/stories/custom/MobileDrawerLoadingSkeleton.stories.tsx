// The `--mobile-*` tokens live behind the `.mobileTheme` class; the app loads
// this in Main.tsx, but Storybook only pulls in index.css, so import it here.
import "~/styles/mobile-theme.css";

import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { MobileDrawerLoadingSkeleton } from "~/pages/workspace/mobile/MobileDrawerLoadingSkeleton";

/**
 * Renders the mobile drawer's loading skeleton inside a drawer-width,
 * `--mobile-surface` column with the real `.workspaceList` padding, so the
 * placeholder geometry can be eyeballed the way it appears on a cold load
 * (before the "No workspaces yet" empty state would otherwise flash).
 */
const Wrapper = (): ReactElement => (
  <div className="mobileTheme" style={{ background: "var(--mobile-surface)", width: "300px", height: "100%" }}>
    <div style={{ padding: "var(--space-1) var(--space-2)" }}>
      <MobileDrawerLoadingSkeleton />
    </div>
  </div>
);

const meta = {
  title: "Custom/MobileDrawerLoadingSkeleton",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
