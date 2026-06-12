import { Strong } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Strong",
  component: Strong,
  args: {
    children: "Bold text",
  },
} satisfies Meta<typeof Strong>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
