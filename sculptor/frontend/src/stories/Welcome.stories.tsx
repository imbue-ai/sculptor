import { Heading, Text } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const Welcome = (): ReactElement => (
  <div>
    <Heading size="5" mb="2">
      Custom Components
    </Heading>
    <Text size="2" color="gray">
      Stories for custom components built on top of Radix Themes will appear here.
    </Text>
  </div>
);

const meta = {
  title: "Custom/Welcome",
  component: Welcome,
} satisfies Meta<typeof Welcome>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
