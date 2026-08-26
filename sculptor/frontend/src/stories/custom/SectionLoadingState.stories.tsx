import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { SectionLoadingState } from "~/components/sections/SectionLoadingState";

/**
 * Renders the section-body loading placeholder inside a panel-sized box that
 * mimics a section's content area, so the skeleton geometry can be eyeballed the
 * way it appears while an agent panel is still resolving after a hard refresh.
 */
const Wrapper = (): ReactElement => (
  <div style={{ background: "var(--color-panel-solid)", width: "620px", height: "360px", display: "flex" }}>
    <SectionLoadingState />
  </div>
);

const meta = {
  title: "Custom/SectionLoadingState",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
