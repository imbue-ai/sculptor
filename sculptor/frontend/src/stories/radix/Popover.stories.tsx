import { Button, Flex, Popover, Text, TextField } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/Popover",
  component: Popover.Root,
} satisfies Meta<typeof Popover.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (): ReactElement => (
    <Popover.Root>
      <Popover.Trigger>
        <Button variant="soft">Open Popover</Button>
      </Popover.Trigger>
      <Popover.Content width="360px">
        <Flex direction="column" gap="3">
          <Text size="2" weight="bold">
            Quick edit
          </Text>
          <TextField.Root placeholder="Enter value" />
          <Flex gap="3" justify="end">
            <Popover.Close>
              <Button variant="soft" color="gray" size="1">
                Cancel
              </Button>
            </Popover.Close>
            <Popover.Close>
              <Button size="1">Save</Button>
            </Popover.Close>
          </Flex>
        </Flex>
      </Popover.Content>
    </Popover.Root>
  ),
};
