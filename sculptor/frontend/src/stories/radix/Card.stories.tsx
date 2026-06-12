import { Card, Flex, Text } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/Card",
  component: Card,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3", "4", "5"],
    },
    variant: {
      control: "select",
      options: ["surface", "classic", "ghost"],
    },
  },
  args: {
    size: "2",
    variant: "surface",
  },
} satisfies Meta<typeof Card>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (args): ReactElement => (
    <Card {...args} style={{ maxWidth: 300 }}>
      <Flex direction="column" gap="2">
        <Text size="3" weight="bold">
          Card title
        </Text>
        <Text size="2" color="gray">
          Card content with some descriptive text.
        </Text>
      </Flex>
    </Card>
  ),
};
