import { Em } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Em",
  component: Em,
  args: {
    children: "Emphasized text",
  },
} satisfies Meta<typeof Em>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
