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

export const GithubSelected: Story = {
  args: { value: "github" },
};

export const GitlabSelected: Story = {
  args: { value: "gitlab" },
};

export const LocalSelected: Story = {
  args: { value: "local" },
};

export const AllDisabled: Story = {
  args: { value: "github", disabled: true },
};
