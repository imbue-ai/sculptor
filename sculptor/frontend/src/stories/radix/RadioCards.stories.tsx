import { RadioCards } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/RadioCards",
  component: RadioCards.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
    columns: {
      control: "select",
      options: ["1", "2", "3"],
    },
  },
  args: {
    size: "2",
    columns: "3",
  },
} satisfies Meta<typeof RadioCards.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <RadioCards.Root {...args} defaultValue="react">
      <RadioCards.Item value="react">React</RadioCards.Item>
      <RadioCards.Item value="vue">Vue</RadioCards.Item>
      <RadioCards.Item value="angular">Angular</RadioCards.Item>
    </RadioCards.Root>
  ),
};
