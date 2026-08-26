import type { Meta, StoryObj } from "@storybook/react-vite";

import { SourceRadioCards } from "~/components/add-repo/SourceRadioCards.tsx";

const noop = (): void => {};

const meta = {
  title: "Custom/Onboarding/SourceRadioCards",
  component: SourceRadioCards,
  args: {
    onValueChange: noop,
  },
} satisfies Meta<typeof SourceRadioCards>;

// eslint-disable-next-line import/no-default-export
export default meta;
type Story = StoryObj<typeof meta>;

// Local is the picker's default source, so it leads here too.
export const LocalSelected: Story = {
  args: { value: "local" },
};

export const GithubSelected: Story = {
  args: { value: "github" },
};

export const AllDisabled: Story = {
  args: { value: "local", disabled: true },
};
