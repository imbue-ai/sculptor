import { SegmentedControl } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/SegmentedControl",
  component: SegmentedControl.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
  },
  args: {
    size: "2",
  },
} satisfies Meta<typeof SegmentedControl.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <SegmentedControl.Root {...args} defaultValue="inbox">
      <SegmentedControl.Item value="inbox">Inbox</SegmentedControl.Item>
      <SegmentedControl.Item value="drafts">Drafts</SegmentedControl.Item>
      <SegmentedControl.Item value="sent">Sent</SegmentedControl.Item>
    </SegmentedControl.Root>
  ),
};
