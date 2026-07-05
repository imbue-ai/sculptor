import { Box, Flex, Progress, Text } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { IndeterminateProgress } from "~/pages/workspace/diffViewer/IndeterminateProgress.tsx";

const meta = {
  title: "Custom/IndeterminateProgress",
  component: IndeterminateProgress,
  argTypes: {
    size: {
      control: "select",
      options: ["1", "2", "3"],
    },
  },
  decorators: [
    (Story): ReactElement => (
      <Box style={{ width: "480px" }}>
        <Story />
      </Box>
    ),
  ],
} satisfies Meta<typeof IndeterminateProgress>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Sizes: Story = {
  render: (): ReactElement => (
    <Flex direction="column" gap="4">
      {(["1", "2", "3"] as const).map((size) => (
        <Flex key={size} direction="column" gap="2">
          <Flex gap="3">
            <Text size="1" color="gray">
              IndeterminateProgress size={size}
            </Text>
            <Text size="1" color="gray">
              vs.
            </Text>
            <Text size="1" color="gray">
              Radix Progress size={size} (value=100)
            </Text>
          </Flex>
          <IndeterminateProgress size={size} />
          <Progress size={size} value={100} />
        </Flex>
      ))}
    </Flex>
  ),
};

export const ComparedWithRadixProgress: Story = {
  render: (): ReactElement => (
    <Flex direction="column" gap="4">
      <Flex direction="column" gap="2">
        <Text size="1" color="gray">
          New IndeterminateProgress
        </Text>
        <IndeterminateProgress />
      </Flex>
      <Flex direction="column" gap="2">
        <Text size="1" color="gray">
          Radix Progress (size 1, indeterminate, duration=2s)
        </Text>
        <Progress size="1" duration="2s" />
      </Flex>
      <Flex direction="column" gap="2">
        <Text size="1" color="gray">
          Radix Progress (size 1, value=100)
        </Text>
        <Progress size="1" value={100} />
      </Flex>
      <Flex direction="column" gap="2">
        <Text size="1" color="gray">
          Radix Progress (size 1, indeterminate, duration=0s)
        </Text>
        <Progress size="1" duration="0s" />
      </Flex>
    </Flex>
  ),
};

export const OnPanelEdge: Story = {
  render: (): ReactElement => (
    <Box
      style={{
        position: "relative",
        height: "120px",
        background: "var(--color-panel-solid)",
        border: "1px solid var(--gray-a4)",
        borderRadius: "var(--radius-2)",
      }}
    >
      <Box style={{ position: "absolute", top: 0, left: 0, right: 0, zIndex: 1 }}>
        <IndeterminateProgress />
      </Box>
      <Flex align="center" justify="center" height="100%">
        <Text size="2" color="gray">
          Loading file diff…
        </Text>
      </Flex>
    </Box>
  ),
};
