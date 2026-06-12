import { RadioGroup } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/RadioGroup",
  component: RadioGroup.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
  },
  args: {
    size: "2",
  },
} satisfies Meta<typeof RadioGroup.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <RadioGroup.Root {...args} defaultValue="email">
      <RadioGroup.Item value="email">Email</RadioGroup.Item>
      <RadioGroup.Item value="sms">SMS</RadioGroup.Item>
      <RadioGroup.Item value="push">Push notification</RadioGroup.Item>
    </RadioGroup.Root>
  ),
};
