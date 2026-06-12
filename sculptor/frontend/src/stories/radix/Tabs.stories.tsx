import { Box, Tabs, Text } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/Tabs",
  component: Tabs.Root,
} satisfies Meta<typeof Tabs.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (): ReactElement => (
    <Tabs.Root defaultValue="account">
      <Tabs.List size="2">
        <Tabs.Trigger value="account">Account</Tabs.Trigger>
        <Tabs.Trigger value="settings">Settings</Tabs.Trigger>
        <Tabs.Trigger value="billing">Billing</Tabs.Trigger>
      </Tabs.List>
      <Box pt="3">
        <Tabs.Content value="account">
          <Text size="2">Manage your account settings.</Text>
        </Tabs.Content>
        <Tabs.Content value="settings">
          <Text size="2">Configure application preferences.</Text>
        </Tabs.Content>
        <Tabs.Content value="billing">
          <Text size="2">View billing and subscription details.</Text>
        </Tabs.Content>
      </Box>
    </Tabs.Root>
  ),
};
