import { Progress } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Progress",
  component: Progress,
  argTypes: {
    value: {
      control: { type: "range", min: 0, max: 100 },
    },
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
    variant: {
      control: "select",
      options: ["classic", "surface", "soft"],
    },
    color: {
      control: "select",
      options: ["gold", "gray", "red", "blue", "green"],
    },
  },
  args: {
    value: 50,
    size: "2",
  },
} satisfies Meta<typeof Progress>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
