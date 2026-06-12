import { TabNav } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/TabNav",
  component: TabNav.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2"],
    },
  },
  args: {
    size: "2",
  },
} satisfies Meta<typeof TabNav.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <TabNav.Root {...args}>
      <TabNav.Link href="#" active>
        Dashboard
      </TabNav.Link>
      <TabNav.Link href="#">Projects</TabNav.Link>
      <TabNav.Link href="#">Settings</TabNav.Link>
    </TabNav.Root>
  ),
};
