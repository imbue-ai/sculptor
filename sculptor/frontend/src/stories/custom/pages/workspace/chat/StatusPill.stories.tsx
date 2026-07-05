import { IconButton, Tooltip } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Check, Square } from "lucide-react";
import type { ComponentType, ReactElement } from "react";

import { ElementIds } from "~/api";
import type { AnimationProps } from "~/pages/workspace/chat/pillAnimations";
import {
  ANIMATION_POOL,
  BouncingDotsAnimation,
  OrbitAnimation,
  SpinnerAnimation,
  WaveDotsAnimation,
} from "~/pages/workspace/chat/pillAnimations";
import styles from "~/pages/workspace/chat/StatusPill.module.scss";

/**
 * StatusPill uses hooks that depend on workspace context (useWorkspacePageParams,
 * useAgentStatus, useElapsedTime), making it hard to render directly in Storybook.
 * Instead we render a visual-only replica that shows the exact same markup and styles.
 */

type PillPreviewProps = {
  label: string;
  elapsed: string;
  isCancellable: boolean;
  isCompacting: boolean;
  Animation: ComponentType<AnimationProps> | null;
};

const PillPreview = ({ label, elapsed, isCancellable, isCompacting, Animation }: PillPreviewProps): ReactElement => {
  const pillClassName = isCompacting ? `${styles.pill} ${styles.pillCompacting}` : styles.pill;
  return (
    <div className={pillClassName} style={{ float: "none" }} data-testid={ElementIds.STATUS_PILL}>
      {Animation ? (
        <Animation data-testid={ElementIds.STATUS_PILL_ANIMATION} />
      ) : (
        <Check size={16} strokeWidth={2} style={{ color: "var(--gray-9)" }} />
      )}
      <span className={styles.label} data-testid={ElementIds.STATUS_PILL_LABEL}>
        {label}
      </span>
      <span className={styles.elapsed} data-testid={ElementIds.STATUS_PILL_ELAPSED}>
        {elapsed}
      </span>
      <Tooltip content={isCancellable ? "Stop ⌘X" : undefined}>
        <IconButton
          size="1"
          variant="ghost"
          className={styles.stopButton}
          style={{ visibility: isCancellable ? "visible" : "hidden" }}
          disabled={!isCancellable}
          data-testid={ElementIds.STATUS_PILL_STOP}
        >
          <Square size={5} fill="currentColor" />
        </IconButton>
      </Tooltip>
    </div>
  );
};

const AllStates = (): ReactElement => {
  const states: ReadonlyArray<PillPreviewProps> = [
    { label: "Thinking...", elapsed: "3.2s", isCancellable: true, isCompacting: false, Animation: OrbitAnimation },
    { label: "Streaming...", elapsed: "5.7s", isCancellable: true, isCompacting: false, Animation: WaveDotsAnimation },
    {
      label: "Calling tools...",
      elapsed: "8.1s",
      isCancellable: true,
      isCompacting: false,
      Animation: BouncingDotsAnimation,
    },
    {
      label: "Compacting...",
      elapsed: "2.0s",
      isCancellable: false,
      isCompacting: true,
      Animation: SpinnerAnimation,
    },
    { label: "Stopping...", elapsed: "1.4s", isCancellable: false, isCompacting: false, Animation: OrbitAnimation },
    { label: "Stopped", elapsed: "1.8s", isCancellable: false, isCompacting: false, Animation: null },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "24px" }}>
      {states.map((props) => (
        <div key={props.label} style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <span style={{ width: "120px", fontSize: "12px", color: "var(--gray-11)" }}>{props.label}</span>
          <PillPreview {...props} />
        </div>
      ))}
    </div>
  );
};

const RandomAnimations = (): ReactElement => (
  <div style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "24px" }}>
    {ANIMATION_POOL.map((Animation, i) => (
      <PillPreview
        key={i}
        label="Thinking..."
        elapsed="3.2s"
        isCancellable={true}
        isCompacting={false}
        Animation={Animation}
      />
    ))}
  </div>
);

const meta = {
  title: "Chat/Status/StatusPill",
  parameters: {
    layout: "centered",
  },
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const States: Story = {
  render: (): ReactElement => <AllStates />,
};

export const WithEachAnimation: Story = {
  render: (): ReactElement => <RandomAnimations />,
};
