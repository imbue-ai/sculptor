import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ComponentType, ReactElement } from "react";

import type { AnimationProps } from "~/pages/workspace/chatAlpha/pillAnimations";
import {
  ANIMATION_POOL,
  AudioBarsAnimation,
  BouncingDotsAnimation,
  CascadeAnimation,
  OrbitAnimation,
  PulsingDot,
  SparkAnimation,
  SpinnerAnimation,
  WaveDotsAnimation,
} from "~/pages/workspace/chatAlpha/pillAnimations";

const NAMED_ANIMATIONS: ReadonlyArray<{ name: string; Component: ComponentType<AnimationProps> }> = [
  { name: "Orbit", Component: OrbitAnimation },
  { name: "Bouncing Dots", Component: BouncingDotsAnimation },
  { name: "Wave Dots", Component: WaveDotsAnimation },
  { name: "Audio Bars", Component: AudioBarsAnimation },
  { name: "Cascade", Component: CascadeAnimation },
  { name: "Spark", Component: SparkAnimation },
  { name: "Spinner (compacting)", Component: SpinnerAnimation },
  { name: "Pulsing Dot (tool exec)", Component: PulsingDot },
];

const AnimationGrid = (): ReactElement => (
  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "24px", padding: "24px" }}>
    {NAMED_ANIMATIONS.map(({ name, Component }) => (
      <div
        key={name}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "8px",
          padding: "16px",
          border: "1px solid var(--gray-6)",
          borderRadius: "8px",
        }}
      >
        <Component />
        <span style={{ fontSize: "12px", color: "var(--gray-11)" }}>{name}</span>
      </div>
    ))}
  </div>
);

const PoolOnly = (): ReactElement => (
  <div style={{ display: "flex", gap: "24px", padding: "24px" }}>
    {ANIMATION_POOL.map((Component, i) => (
      <div key={i} style={{ padding: "12px", border: "1px solid var(--gray-6)", borderRadius: "8px" }}>
        <Component />
      </div>
    ))}
  </div>
);

const meta = {
  title: "Chat Alpha/Status/PillAnimations",
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const AllAnimations: Story = {
  render: (): ReactElement => <AnimationGrid />,
};

export const Pool: Story = {
  render: (): ReactElement => <PoolOnly />,
};
