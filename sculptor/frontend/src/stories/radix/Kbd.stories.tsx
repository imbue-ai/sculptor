import { Kbd } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Kbd",
  component: Kbd,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
    },
  },
  args: {
    size: "3",
    children: "Enter",
  },
} satisfies Meta<typeof Kbd>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
