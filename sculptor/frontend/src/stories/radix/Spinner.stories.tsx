import { Spinner } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Spinner",
  component: Spinner,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
  },
  args: {
    size: "2",
  },
} satisfies Meta<typeof Spinner>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
