import { Link } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Link",
  component: Link,
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
      options: ["gold", "gray", "red", "blue", "green"],
    },
    underline: {
      control: "select",
      options: ["auto", "always", "hover", "none"],
    },
  },
  args: {
    size: "3",
    children: "Click me",
    href: "#",
  },
} satisfies Meta<typeof Link>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
