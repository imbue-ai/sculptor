import { TextField } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/TextField",
  component: TextField.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
    variant: {
      control: "select",
      options: ["classic", "surface", "soft"],
    },
    placeholder: { control: "text" },
  },
  args: {
    size: "2",
    variant: "surface",
    placeholder: "Enter text...",
  },
} satisfies Meta<typeof TextField.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
