import { Button } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Button",
  component: Button,
  argTypes: {
    variant: {
      control: "select",
      options: ["classic", "solid", "soft", "surface", "outline", "ghost"],
    },
    size: {
      control: "select",
      options: ["1", "2", "3", "4"],
    },
    color: {
      control: "select",
      options: ["gold", "gray", "red", "blue", "green"],
    },
  },
  args: {
    variant: "solid",
    size: "2",
    children: "Button",
  },
} satisfies Meta<typeof Button>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
