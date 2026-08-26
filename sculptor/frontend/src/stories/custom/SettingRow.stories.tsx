import {
  Box,
  Button,
  Code,
  Flex,
  IconButton,
  SegmentedControl,
  Select,
  Switch,
  Text,
  TextArea,
  TextField,
} from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Monitor, Moon, RefreshCw, Sun } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import { SettingRow } from "~/pages/settings/components/SettingRow.tsx";

const meta = {
  title: "Custom/SettingRow",
  component: SettingRow,
  decorators: [
    (Story): ReactElement => (
      <div style={{ width: "700px" }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SettingRow>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const WithSwitch: Story = {
  args: {
    title: "Smooth Streaming",
    description: "Smoothly animate text as it streams in, rather than showing it in bursts.",
    children: <Switch />,
  },
};

export const WithSelect: Story = {
  args: {
    title: "Default Model",
    description: "Select the default model for new Agents.",
    children: (
      <Select.Root defaultValue="claude-sonnet">
        <Select.Trigger variant="soft" />
        <Select.Content>
          <Select.Item value="most-recent">Most Recently Used</Select.Item>
          <Select.Item value="claude-sonnet">Claude Sonnet</Select.Item>
          <Select.Item value="claude-opus">Claude Opus</Select.Item>
        </Select.Content>
      </Select.Root>
    ),
  },
};

export const WithTextField: Story = {
  args: {
    title: "Custom Backend Command",
    description: "Shell command to launch the backend. Leave empty for default local mode.",
    children: <TextField.Root placeholder="e.g., docker run ..." style={{ minWidth: "300px" }} />,
  },
};

export const WithNumberField: Story = {
  args: {
    title: "Minimum free disk space",
    description: "Sculptor stops allowing new tasks below this threshold.",
    children: (
      <Flex align="center" gap="2">
        <TextField.Root type="number" defaultValue="2" min={1} max={100} step={1} style={{ width: 80 }} />
        <Text size="2">GB</Text>
      </Flex>
    ),
  },
};

export const WithSegmentedControl: Story = {
  args: {
    title: "Appearance",
    description: "Control light mode, dark mode, or follow system preference.",
    children: (
      <SegmentedControl.Root defaultValue="system">
        <SegmentedControl.Item value="light">
          <Flex align="center" gap="1">
            <Sun size={16} />
            Light
          </Flex>
        </SegmentedControl.Item>
        <SegmentedControl.Item value="dark">
          <Flex align="center" gap="1">
            <Moon size={16} />
            Dark
          </Flex>
        </SegmentedControl.Item>
        <SegmentedControl.Item value="system">
          <Flex align="center" gap="1">
            <Monitor size={16} />
            System
          </Flex>
        </SegmentedControl.Item>
      </SegmentedControl.Root>
    ),
  },
};

export const WithIconButton: Story = {
  args: {
    title: "Loaded variables",
    description: "Variables loaded from .env files across your repos.",
    children: (
      <IconButton variant="ghost" size="1" title="Refresh">
        <RefreshCw size={14} />
      </IconButton>
    ),
  },
};

export const ReadOnlyDisplay: Story = {
  args: {
    title: "Active Version",
    description: "Currently resolved Claude CLI version.",
    children: <Text size="2">1.2.3</Text>,
  },
};

export const WithTextAreaFooter: Story = {
  args: {
    title: "Commit prompt",
    description: "The prompt sent to the agent when you click Commit Changes.",
    children: <span />,
    footer: (
      <Flex direction="column" gap="2" mt="2" width="100%">
        <TextArea defaultValue="Write a clear, concise commit message..." rows={4} style={{ width: "100%" }} />
        <Flex justify="end">
          <Button variant="soft" size="1">
            Reset to default
          </Button>
        </Flex>
      </Flex>
    ),
  },
};

export const WithDocumentationFooter: Story = {
  args: {
    title: "Environment variables",
    description: "Load environment variables from .env files into your agent sessions.",
    children: <span />,
    footer: (
      <Flex direction="column" gap="1" mt="2">
        <Text size="2" as="p" style={{ color: "var(--gray-11)" }}>
          <Text weight="bold">Global (all repos):</Text> Place a <Code size="2">.env</Code> file at{" "}
          <Code size="2">~/.sculptor/.env</Code>
        </Text>
        <Text size="2" as="p" style={{ color: "var(--gray-11)" }}>
          <Text weight="bold">Per-repo:</Text> Place a <Code size="2">.env</Code> file at the root of your repository.
        </Text>
      </Flex>
    ),
  },
};

export const WithMultipleControls: Story = {
  args: {
    title: "Software Updates",
    description: "You are on the latest version (v2.1.0).",
    children: (
      <Flex align="center" gap="2">
        <Select.Root defaultValue="STABLE">
          <Select.Trigger variant="soft" />
          <Select.Content>
            <Select.Item value="STABLE">Stable</Select.Item>
            <Select.Item value="RC">Latest</Select.Item>
          </Select.Content>
        </Select.Root>
        <Button variant="soft">Check for updates</Button>
      </Flex>
    ),
  },
};

export const WithInlineLabelAndFooter: Story = {
  args: {
    title: "Accent color",
    description: "The primary color used for interactive elements.",
    children: (
      <Text size="2" style={{ color: "var(--gray-11)" }}>
        indigo
      </Text>
    ),
    footer: (
      <Flex gap="2" mt="2" wrap="wrap">
        {["tomato", "red", "crimson", "pink", "plum", "purple", "violet", "indigo", "blue", "cyan"].map((color) => (
          <Box
            key={color}
            style={{
              width: 24,
              height: 24,
              borderRadius: "var(--radius-2)",
              background: `var(--${color}-9)`,
              cursor: "pointer",
            }}
          />
        ))}
      </Flex>
    ),
  },
};

export const WithReactNodeDescription: Story = {
  args: {
    title: "Custom Setting",
    description: (
      <span>
        This description contains <strong>bold text</strong> and a <Code size="2">code snippet</Code>.
      </span>
    ),
    children: <Switch />,
  },
};

export const WithTestId: Story = {
  args: {
    title: "Testable Setting",
    description: "This row has a data-testid for integration tests.",
    children: <Switch />,
    "data-testid": "my-setting-row",
  },
};

const MultipleRowsExample = (): ReactElement => {
  const [isSmoothStreaming, setIsSmoothStreaming] = useState(true);
  const [model, setModel] = useState("claude-sonnet");
  const [appearance, setAppearance] = useState("system");

  return (
    <>
      <SettingRow title="Default Model" description="Select the default model for new Agents.">
        <Select.Root value={model} onValueChange={setModel}>
          <Select.Trigger variant="soft" />
          <Select.Content>
            <Select.Item value="most-recent">Most Recently Used</Select.Item>
            <Select.Item value="claude-sonnet">Claude Sonnet</Select.Item>
            <Select.Item value="claude-opus">Claude Opus</Select.Item>
          </Select.Content>
        </Select.Root>
      </SettingRow>
      <SettingRow title="Theme" description="Control the appearance of Sculptor.">
        <Select.Root value={appearance} onValueChange={setAppearance}>
          <Select.Trigger variant="soft" />
          <Select.Content>
            <Select.Item value="light">Light</Select.Item>
            <Select.Item value="dark">Dark</Select.Item>
            <Select.Item value="system">System</Select.Item>
          </Select.Content>
        </Select.Root>
      </SettingRow>
      <SettingRow
        title="Smooth Streaming"
        description="Smoothly animate text as it streams in, rather than showing it in bursts."
      >
        <Switch checked={isSmoothStreaming} onCheckedChange={setIsSmoothStreaming} />
      </SettingRow>
    </>
  );
};

export const MultipleRows: StoryObj<typeof meta> = {
  render: () => <MultipleRowsExample />,
  args: {
    title: "",
    description: "",
    children: null,
  },
};
