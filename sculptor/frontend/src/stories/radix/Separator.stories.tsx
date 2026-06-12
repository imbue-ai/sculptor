import { Separator } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Separator",
  component: Separator,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3", "4"],
    },
    orientation: {
      control: "select",
      options: ["horizontal", "vertical"],
    },
    color: {
      control: "select",
      options: ["gold", "gray", "red", "blue", "green"],
    },
  },
  args: {
    size: "4",
    orientation: "horizontal",
  },
} satisfies Meta<typeof Separator>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
