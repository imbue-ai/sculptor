import { Avatar } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Avatar",
  component: Avatar,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
    },
    variant: {
      control: "select",
      options: ["solid", "soft"],
    },
    color: {
      control: "select",
      options: ["gold", "gray", "red", "blue", "green"],
    },
  },
  args: {
    size: "3",
    variant: "solid",
    fallback: "JD",
  },
} satisfies Meta<typeof Avatar>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
