import type { Meta, StoryObj } from "@storybook/react-vite";
import { Provider as JotaiProvider } from "jotai";
import { Coins, Info, Terminal } from "lucide-react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { DockingLayout } from "~/components/panels/DockingLayout";
import { PanelRegistryProvider } from "~/components/panels/PanelRegistryProvider";
import type { PanelDefinition } from "~/components/panels/types.ts";

const InfoPanel = (): ReactElement => {
  return (
    <div style={{ padding: "12px", height: "100%", boxSizing: "border-box" }}>
      <div style={{ fontWeight: 600, marginBottom: "8px" }}>Info</div>
      <div style={{ fontSize: "13px", color: "var(--gray-a11)" }}>Project information and metadata</div>
    </div>
  );
};

const CostPanel = (): ReactElement => {
  return (
    <div style={{ padding: "12px", height: "100%", boxSizing: "border-box" }}>
      <div style={{ fontWeight: 600, marginBottom: "8px" }}>Cost</div>
      <div style={{ fontSize: "13px", color: "var(--gray-a11)" }}>Cost tracking and usage metrics</div>
    </div>
  );
};

const TerminalPanel = (): ReactElement => {
  return (
    <div
      style={{
        padding: "12px",
        height: "100%",
        boxSizing: "border-box",
        backgroundColor: "var(--gray-1)",
        fontFamily: "monospace",
        fontSize: "13px",
        color: "var(--gray-a11)",
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: "8px", color: "var(--gray-12)" }}>Terminal</div>
      <div>$ ready</div>
    </div>
  );
};

const DEFAULT_PANELS: ReadonlyArray<PanelDefinition> = [
  {
    id: "info",
    displayName: "Info",
    description: "Storybook panel",
    icon: Info,
    defaultZone: "top-left",
    defaultShortcut: "Cmd+1",
    component: InfoPanel,
  },
  {
    id: "cost",
    displayName: "Cost",
    description: "Storybook panel",
    icon: Coins,
    defaultZone: "top-left",
    defaultShortcut: "Cmd+4",
    component: CostPanel,
  },
  {
    id: "terminal",
    displayName: "Terminal",
    description: "Storybook panel",
    icon: Terminal,
    defaultZone: "bottom",
    defaultShortcut: "Cmd+2",
    component: TerminalPanel,
  },
];

const DockingLayoutStory = (): ReactElement => {
  return (
    <MemoryRouter>
      <JotaiProvider>
        <PanelRegistryProvider panels={DEFAULT_PANELS}>
          <div style={{ width: "100vw", height: "100vh" }}>
            <DockingLayout />
          </div>
        </PanelRegistryProvider>
      </JotaiProvider>
    </MemoryRouter>
  );
};

const meta = {
  title: "Custom/Panels/DockingLayout",
  component: DockingLayout,
  parameters: {
    panelsFullscreen: true,
  },
} satisfies Meta<typeof DockingLayout>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => <DockingLayoutStory />,
};
