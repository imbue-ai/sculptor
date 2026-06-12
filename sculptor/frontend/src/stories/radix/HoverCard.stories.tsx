import { Flex, HoverCard, Link, Text } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

const meta = {
  title: "Radix/HoverCard",
  component: HoverCard.Root,
} satisfies Meta<typeof HoverCard.Root>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: (): ReactElement => (
    <Text size="3">
      Hover over{" "}
      <HoverCard.Root>
        <HoverCard.Trigger>
          <Link href="#">this link</Link>
        </HoverCard.Trigger>
        <HoverCard.Content maxWidth="300px">
          <Flex direction="column" gap="2">
            <Text size="2" weight="bold">
              Preview
            </Text>
            <Text size="2">This is additional information shown on hover.</Text>
          </Flex>
        </HoverCard.Content>
      </HoverCard.Root>{" "}
      to see more info.
    </Text>
  ),
};
