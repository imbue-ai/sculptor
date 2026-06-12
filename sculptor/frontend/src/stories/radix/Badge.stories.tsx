import { Badge } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Badge",
  component: Badge,
  argTypes: {
    variant: {
      control: "select",
      options: ["solid", "soft", "surface", "outline"],
    },
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
    color: {
      control: "select",
      options: ["gold", "gray", "red", "blue", "green", "orange"],
    },
  },
  args: {
    variant: "soft",
    size: "1",
    children: "Badge",
  },
} satisfies Meta<typeof Badge>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
