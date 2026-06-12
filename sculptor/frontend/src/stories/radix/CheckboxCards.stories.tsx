import { CheckboxCards } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/CheckboxCards",
  component: CheckboxCards.Root,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
    columns: {
      control: "select",
      options: ["1", "2", "3"],
    },
  },
  args: {
    size: "2",
    columns: "2",
  },
} satisfies Meta<typeof CheckboxCards.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <CheckboxCards.Root {...args} defaultValue={["react"]}>
      <CheckboxCards.Item value="react">React</CheckboxCards.Item>
      <CheckboxCards.Item value="vue">Vue</CheckboxCards.Item>
      <CheckboxCards.Item value="angular">Angular</CheckboxCards.Item>
      <CheckboxCards.Item value="svelte">Svelte</CheckboxCards.Item>
    </CheckboxCards.Root>
  ),
};
