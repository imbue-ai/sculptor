import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { WorkspaceInitializationStrategy } from "~/api";
import { BranchNameField } from "~/components/newWorkspace/BranchNameField";

const noop = (): void => {};

/**
 * Renders the plain-variant BranchNameField the way the new-workspace form does:
 * as an editable subtitle beneath the workspace title, so the sparkles button's
 * spacing and loading animation can be eyeballed in context.
 */
const Wrapper = (props: { value: string; isLoading: boolean; isManuallyEdited: boolean }): ReactElement => (
  <div style={{ background: "var(--color-panel-solid)", padding: "24px", width: "460px" }}>
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
      <div
        style={{
          color: "var(--gray-12)",
          fontSize: "var(--font-size-5)",
          fontWeight: "var(--font-weight-semibold)",
        }}
      >
        Untitled workspace
      </div>
      <BranchNameField
        mode={WorkspaceInitializationStrategy.WORKTREE}
        value={props.value}
        isManuallyEdited={props.isManuallyEdited}
        isLoading={props.isLoading}
        collision="available"
        onUserEdit={noop}
        onShuffle={noop}
        variant="plain"
      />
    </div>
  </div>
);

const meta = {
  title: "Custom/BranchNameField",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Idle: Story = {
  args: {
    value: "bryden/bold-armadillo",
    isLoading: false,
    isManuallyEdited: false,
  },
};

// A cold open with no name yet: the field shows a skeleton while the first
// auto-filled name is fetched.
export const ColdLoading: Story = {
  args: {
    value: "",
    isLoading: true,
    isManuallyEdited: false,
  },
};

// A re-roll of an existing name: the field keeps the current value and the
// sparkle pulses to signal the fetch (no skeleton).
export const Generating: Story = {
  args: {
    value: "bryden/bold-armadillo",
    isLoading: true,
    isManuallyEdited: false,
  },
};
