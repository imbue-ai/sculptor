import { Heading } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Heading",
  component: Heading,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
    },
    weight: {
      control: "select",
      options: ["light", "regular", "medium", "bold"],
    },
    color: {
      control: "select",
      options: ["gray", "gold", "blue", "red", "green"],
    },
    align: {
      control: "select",
      options: ["left", "center", "right"],
    },
  },
  args: {
    size: "6",
    weight: "bold",
    children: "Heading text",
  },
} satisfies Meta<typeof Heading>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
