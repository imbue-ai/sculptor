import { DataList } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/DataList",
  component: DataList.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
    orientation: {
      control: "select",
      options: ["horizontal", "vertical"],
    },
  },
  args: {
    size: "2",
    orientation: "horizontal",
  },
} satisfies Meta<typeof DataList.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <DataList.Root {...args}>
      <DataList.Item>
        <DataList.Label>Name</DataList.Label>
        <DataList.Value>Jane Doe</DataList.Value>
      </DataList.Item>
      <DataList.Item>
        <DataList.Label>Email</DataList.Label>
        <DataList.Value>jane@example.com</DataList.Value>
      </DataList.Item>
      <DataList.Item>
        <DataList.Label>Role</DataList.Label>
        <DataList.Value>Administrator</DataList.Value>
      </DataList.Item>
    </DataList.Root>
  ),
};
