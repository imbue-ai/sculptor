import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { SidebarLoadingSkeleton } from "~/components/nav/SidebarLoadingSkeleton";

/**
 * Renders the sidebar loading skeleton inside a rail-width, `--gray-2` column
 * that mimics the real sidebar's `.repoList` padding, so the placeholder
 * geometry can be eyeballed the way it appears after a hard refresh.
 */
const Wrapper = (): ReactElement => (
  <div style={{ background: "var(--gray-2)", width: "240px", height: "100%" }}>
    <div style={{ padding: "var(--space-1) var(--space-2)" }}>
      <SidebarLoadingSkeleton />
    </div>
  </div>
);

const meta = {
  title: "Custom/SidebarLoadingSkeleton",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
