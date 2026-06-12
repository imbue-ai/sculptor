import { CheckboxGroup } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/CheckboxGroup",
  component: CheckboxGroup.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
  },
  args: {
    size: "2",
  },
} satisfies Meta<typeof CheckboxGroup.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <CheckboxGroup.Root {...args} defaultValue={["email"]}>
      <CheckboxGroup.Item value="email">Email</CheckboxGroup.Item>
      <CheckboxGroup.Item value="sms">SMS</CheckboxGroup.Item>
      <CheckboxGroup.Item value="push">Push notification</CheckboxGroup.Item>
    </CheckboxGroup.Root>
  ),
};
