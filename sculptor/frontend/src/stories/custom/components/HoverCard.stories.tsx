import { Button, Flex, Link, Text } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { HoverCard } from "~/components/HoverCard";

const meta = {
  title: "Custom/HoverCard",
  component: HoverCard,
  args: {
    trigger: <span>trigger</span>,
    content: <span>content</span>,
  },
} satisfies Meta<typeof HoverCard>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const WithLink: Story = {
  render: (): ReactElement => (
    <Text as="p" size="2">
      Hover over{" "}
      <HoverCard
        trigger={
          <Link href="#" underline="always">
            @alice
          </Link>
        }
        content={
          <Flex direction="column" gap="2" style={{ maxWidth: 260, padding: "var(--space-3)" }}>
            <Text as="div" size="2" weight="bold">
              Alice Johnson
            </Text>
            <Text as="div" size="1" color="gray">
              Frontend engineer working on the design system.
            </Text>
            <Link href="#" size="1">
              View profile
            </Link>
          </Flex>
        }
      />{" "}
      to see their profile card.
    </Text>
  ),
};

export const WithActions: Story = {
  render: (): ReactElement => (
    <Text as="p" size="2">
      Hover over{" "}
      <HoverCard
        trigger={
          <Link href="#" underline="always">
            src/utils/parser.ts
          </Link>
        }
        content={
          <Flex direction="column" gap="2" style={{ maxWidth: 240, padding: "var(--space-3)" }}>
            <Text as="div" size="2" weight="bold">
              parser.ts
            </Text>
            <Text as="div" size="1" color="gray">
              src/utils/parser.ts
            </Text>
            <Flex gap="2">
              <Button size="1" variant="soft">
                Open file
              </Button>
              <Button size="1" variant="soft">
                Copy path
              </Button>
            </Flex>
          </Flex>
        }
      />{" "}
      for quick actions.
    </Text>
  ),
};

export const Positions: Story = {
  render: (): ReactElement => (
    <Flex align="center" justify="center" gap="6" style={{ padding: 120 }}>
      {(["top", "bottom", "left", "right"] as const).map((side) => (
        <HoverCard
          key={side}
          side={side}
          trigger={
            <Button variant="outline" size="1">
              {side}
            </Button>
          }
          content={
            <Text as="div" size="1" style={{ padding: "var(--space-3)" }}>
              Content on the {side}
            </Text>
          }
        />
      ))}
    </Flex>
  ),
};
