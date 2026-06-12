import { Skeleton } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = {
  title: "Radix/Skeleton",
  component: Skeleton,
  args: {
    width: "200px",
    height: "20px",
  },
} satisfies Meta<typeof Skeleton>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
