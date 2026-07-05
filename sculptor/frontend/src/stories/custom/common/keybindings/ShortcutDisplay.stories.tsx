import { Badge, Code, Flex, Heading, Separator, Text, Tooltip } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { formatShortcutForDisplay } from "~/common/keybindings/format";
import { getMetaKey } from "~/electron/platform";

type ShortcutEntry = {
  raw: string;
  description: string;
};

const MACOS_SHORTCUTS: Array<ShortcutEntry> = [
  { raw: "Cmd+K", description: "Search agents" },
  { raw: "Cmd+T", description: "New workspace" },
  { raw: "Cmd+W", description: "Close workspace" },
  { raw: "Cmd+I", description: "Focus input" },
  { raw: "Cmd+F", description: "Chat search" },
  { raw: "Cmd+P", description: "File browser" },
  { raw: "Cmd+?", description: "Keyboard shortcuts" },
  { raw: "Ctrl+Tab", description: "Next tab" },
  { raw: "Ctrl+Shift+Tab", description: "Previous tab" },
  { raw: "Shift+Enter", description: "Newline" },
];

const LINUX_SHORTCUTS: Array<ShortcutEntry> = [
  { raw: "Ctrl+K", description: "Search agents" },
  { raw: "Ctrl+T", description: "New workspace" },
  { raw: "Ctrl+W", description: "Close workspace" },
  { raw: "Ctrl+I", description: "Focus input" },
  { raw: "Ctrl+F", description: "Chat search" },
  { raw: "Ctrl+P", description: "File browser" },
  { raw: "Ctrl+?", description: "Keyboard shortcuts" },
  { raw: "Ctrl+Tab", description: "Next tab" },
  { raw: "Ctrl+Shift+Tab", description: "Previous tab" },
  { raw: "Shift+Enter", description: "Newline" },
];

/**
 * Simulate formatShortcutForDisplay for a specific platform,
 * so we can preview both macOS and Linux rendering on any machine.
 */
const formatForPlatform = (shortcut: string, isMacOS: boolean): string => {
  const separator = isMacOS ? "" : "+";

  return shortcut
    .split("+")
    .map((part) => {
      const trimmed = part.trim().toLowerCase();
      switch (trimmed) {
        case "cmd":
        case "meta":
          return isMacOS ? "⌘" : "Ctrl";
        case "ctrl":
        case "control":
          return isMacOS ? "⌃" : "Ctrl";
        case "alt":
        case "option":
          return isMacOS ? "⌥" : "Alt";
        case "shift":
          return isMacOS ? "⇧" : "Shift";
        default:
          return part.trim().toUpperCase();
      }
    })
    .join(separator);
};

const metaKeyForPlatform = (isMacOS: boolean): string => (isMacOS ? "⌘" : "Ctrl");

const PlatformShortcutTable = ({
  isMacOS,
  platformLabel,
}: {
  isMacOS: boolean;
  platformLabel: string;
}): ReactElement => {
  const metaKey = metaKeyForPlatform(isMacOS);
  const shortcuts = isMacOS ? MACOS_SHORTCUTS : LINUX_SHORTCUTS;

  return (
    <Flex direction="column" gap="4" style={{ maxWidth: "500px" }}>
      <Heading size="4">
        Shortcut Display — {platformLabel} {isMacOS ? "🍎" : "🐧"}
      </Heading>
      <Text size="2" color="gray">
        Modifier key: <Code>{metaKey}</Code>
      </Text>
      <Separator size="4" />

      <Flex direction="column" gap="2">
        <Flex gap="4" style={{ fontWeight: "bold" }}>
          <Text size="2" style={{ width: "160px" }}>
            Raw shortcut
          </Text>
          <Text size="2" style={{ width: "160px" }}>
            Displayed as
          </Text>
          <Text size="2">Context</Text>
        </Flex>
        {shortcuts.map(({ raw, description }) => (
          <Flex key={raw} gap="4" align="center">
            <Code size="2" style={{ width: "160px" }}>
              {raw}
            </Code>
            <Badge size="2" variant="soft" style={{ minWidth: "160px" }}>
              {formatForPlatform(raw, isMacOS)}
            </Badge>
            <Text size="1" color="gray">
              {description}
            </Text>
          </Flex>
        ))}
      </Flex>

      <Separator size="4" />

      <Heading size="3">In-context examples</Heading>

      <Flex direction="column" gap="3">
        <Text size="2">
          <strong>Tooltip style:</strong>
        </Text>
        <Flex gap="2">
          <Tooltip content={`${metaKey}⏎ to send message`}>
            <Badge size="2" variant="surface" style={{ cursor: "pointer" }}>
              Hover me (send tooltip)
            </Badge>
          </Tooltip>
          <Tooltip content={`Search for agents (${formatForPlatform(isMacOS ? "Cmd+K" : "Ctrl+K", isMacOS)})`}>
            <Badge size="2" variant="surface" style={{ cursor: "pointer" }}>
              Hover me (search tooltip)
            </Badge>
          </Tooltip>
        </Flex>

        <Text size="2">
          <strong>Hint bar style (like ComboInput):</strong>
        </Text>
        <Flex
          justify="between"
          style={{
            padding: "6px 12px",
            background: "var(--gray-2)",
            borderRadius: "var(--radius-2)",
            fontSize: "12px",
            color: "var(--gray-9)",
          }}
        >
          <Flex gap="3">
            <span>{metaKey}I focus</span>
            <span>↑↓ navigation</span>
          </Flex>
          <span>{metaKey} ↵ to create workspace</span>
        </Flex>
      </Flex>
    </Flex>
  );
};

const LiveShortcutTable = (): ReactElement => (
  <Flex direction="column" gap="4" style={{ maxWidth: "500px" }}>
    <Heading size="4">Shortcut Display — Live (this platform)</Heading>
    <Text size="2" color="gray">
      Using runtime <Code>getMetaKey()</Code> = <Code>{getMetaKey()}</Code>
    </Text>
    <Separator size="4" />

    <Flex direction="column" gap="2">
      <Flex gap="4" style={{ fontWeight: "bold" }}>
        <Text size="2" style={{ width: "160px" }}>
          Raw shortcut
        </Text>
        <Text size="2" style={{ width: "160px" }}>
          Displayed as
        </Text>
        <Text size="2">Context</Text>
      </Flex>
      {MACOS_SHORTCUTS.map(({ raw, description }) => (
        <Flex key={raw} gap="4" align="center">
          <Code size="2" style={{ width: "160px" }}>
            {raw}
          </Code>
          <Badge size="2" variant="soft" style={{ minWidth: "160px" }}>
            {formatShortcutForDisplay(raw)}
          </Badge>
          <Text size="1" color="gray">
            {description}
          </Text>
        </Flex>
      ))}
    </Flex>
  </Flex>
);

const SideBySide = (): ReactElement => (
  <Flex gap="6" wrap="wrap">
    <PlatformShortcutTable isMacOS={true} platformLabel="macOS" />
    <PlatformShortcutTable isMacOS={false} platformLabel="Linux" />
  </Flex>
);

const meta = {
  title: "Custom/ShortcutDisplay",
  component: SideBySide,
} satisfies Meta<typeof SideBySide>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const MacOS: StoryObj<Meta<typeof PlatformShortcutTable>> = {
  render: () => <PlatformShortcutTable isMacOS={true} platformLabel="macOS" />,
};

export const Linux: StoryObj<Meta<typeof PlatformShortcutTable>> = {
  render: () => <PlatformShortcutTable isMacOS={false} platformLabel="Linux" />,
};

export const Live: StoryObj<Meta<typeof LiveShortcutTable>> = {
  render: () => <LiveShortcutTable />,
};
