import { IconButton } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Plus } from "lucide-react";
import type { ReactElement } from "react";

import { TabBar } from "~/components/tabs/TabBar";
import type { TabDefinition } from "~/components/tabs/types";

import { getTabStatusIcon } from "./TerminalConnectionIndicator";

// Illustrates the connection-state indicator a terminal tab shows: nothing when
// healthy, an amber pulsing dot while reconnecting, a red dot when the
// connection won't recover on its own. Uses the real `getTabStatusIcon`, so the
// dots and colors match the app exactly.
const STATUS_TABS: ReadonlyArray<TabDefinition> = [
  { id: "term-connected", label: "Connected", icon: getTabStatusIcon("connected") },
  { id: "term-reconnecting", label: "Reconnecting", icon: getTabStatusIcon("reconnecting") },
  { id: "term-disconnected", label: "Disconnected", icon: getTabStatusIcon("disconnected") },
];

const noop = (): void => undefined;

const TerminalTabStatusDemo = (): ReactElement => (
  <div style={{ width: "100%", border: "1px solid var(--gray-a5)" }}>
    <TabBar
      tabs={[...STATUS_TABS]}
      openTabIds={STATUS_TABS.map((t) => t.id)}
      activeTabId="term-reconnecting"
      onActivate={noop}
      onClose={noop}
      onReorder={noop}
      variant="compact"
      alwaysCloseable
    >
      <IconButton variant="ghost" size="1" color="gray" aria-label="Add terminal">
        <Plus size={14} />
      </IconButton>
    </TabBar>
  </div>
);

const meta = {
  title: "Custom/Tabs/TerminalTabStatus",
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const ConnectionStates: Story = {
  render: () => <TerminalTabStatusDemo />,
};
