import { Quote } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Quote",
  component: Quote,
  args: {
    children: "To be, or not to be, that is the question.",
  },
} satisfies Meta<typeof Quote>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
