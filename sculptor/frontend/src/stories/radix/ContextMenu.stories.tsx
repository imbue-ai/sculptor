import { Box, ContextMenu, Text } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/ContextMenu",
  component: ContextMenu.Root,
} satisfies Meta<typeof ContextMenu.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (): ReactElement => (
    <ContextMenu.Root>
      <ContextMenu.Trigger>
        <Box
          p="6"
          style={{
            backgroundColor: "var(--accent-3)",
            borderRadius: "var(--radius-3)",
            border: "2px dashed var(--accent-6)",
          }}
        >
          <Text size="2">Right-click here</Text>
        </Box>
      </ContextMenu.Trigger>
      <ContextMenu.Content>
        <ContextMenu.Item>Cut</ContextMenu.Item>
        <ContextMenu.Item>Copy</ContextMenu.Item>
        <ContextMenu.Item>Paste</ContextMenu.Item>
        <ContextMenu.Separator />
        <ContextMenu.Item color="red">Delete</ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  ),
};
