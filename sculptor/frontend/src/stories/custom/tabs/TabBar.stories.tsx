import { DropdownMenu, Flex, IconButton } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  Activity,
  Columns2,
  FileText,
  Home,
  Loader2,
  Maximize2,
  MoreVertical,
  Plus,
  Search,
  Settings,
  SplitSquareHorizontal,
  Terminal,
  Users,
  WrapText,
  X,
  Zap,
} from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useRef, useState } from "react";

import { TabBar } from "~/components/tabs/TabBar";
import type { TabDefinition } from "~/components/tabs/types";

const SpinningIcon = ({ children }: { children: ReactNode }): ReactElement => {
  return <span style={{ display: "flex", animation: "spin 1.5s linear infinite" }}>{children}</span>;
};

const ALL_TABS: ReadonlyArray<TabDefinition> = [
  {
    id: "tab-1",
    label: "Home",
    icon: <Home width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Welcome to the home tab.</div>,
    preview: (
      <div>
        <strong>Home</strong>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--gray-a11)" }}>Overview and quick actions</p>
      </div>
    ),
  },
  {
    id: "tab-2",
    label: "Settings",
    icon: <Settings width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Application settings and preferences.</div>,
    preview: (
      <div>
        <strong>Settings</strong>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--gray-a11)" }}>Configure your workspace</p>
      </div>
    ),
  },
  {
    id: "tab-3",
    label: "Documents",
    icon: <FileText width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Your documents and files.</div>,
  },
  {
    id: "tab-4",
    label: "Terminal",
    icon: <Terminal width={14} height={14} />,
    content: <div style={{ padding: 16, fontFamily: "monospace", background: "var(--gray-1)" }}>$ _</div>,
  },
  {
    id: "tab-5",
    label: "Activity",
    icon: <Activity width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Recent activity log.</div>,
    preview: (
      <div>
        <strong>Activity</strong>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--gray-a11)" }}>3 new events today</p>
      </div>
    ),
  },
  {
    id: "tab-6",
    label: "Search",
    icon: <Search width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Search across all content.</div>,
  },
  {
    id: "tab-7",
    label: "Users",
    icon: <Users width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Team members and permissions.</div>,
  },
  {
    id: "tab-8",
    label: "Background Processing Queue",
    icon: (
      <SpinningIcon>
        <Loader2 width={14} height={14} />
      </SpinningIcon>
    ),
    content: <div style={{ padding: 16 }}>Processing 12 items...</div>,
    preview: (
      <div>
        <strong>Processing Queue</strong>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--gray-a11)" }}>12 items in queue, 3 active</p>
      </div>
    ),
  },
  {
    id: "tab-9",
    label: "Quick Actions",
    icon: <Zap width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Frequently used actions and shortcuts.</div>,
  },
  {
    id: "tab-10",
    label: "File Explorer",
    icon: <FileText width={14} height={14} />,
    content: <div style={{ padding: 16 }}>Browse project files and folders.</div>,
  },
];

const DEFAULT_OPEN_TAB_IDS = ["tab-1", "tab-2", "tab-3"];

const TabBarDemo = (): ReactElement => {
  const [openTabIds, setOpenTabIds] = useState<Array<string>>(DEFAULT_OPEN_TAB_IDS);
  const [activeTabId, setActiveTabId] = useState<string>("tab-1");
  const tabHistoryRef = useRef<Array<string>>(["tab-1"]);

  const handleActivate = useCallback((tabId: string): void => {
    tabHistoryRef.current = [...tabHistoryRef.current, tabId];
    setActiveTabId(tabId);
  }, []);

  const handleClose = useCallback(
    (tabId: string): void => {
      const nextOpenTabIds = openTabIds.filter((id) => id !== tabId);
      if (nextOpenTabIds.length === 0) return;

      setOpenTabIds(nextOpenTabIds);

      if (tabId === activeTabId) {
        const history = tabHistoryRef.current.filter((id) => id !== tabId && nextOpenTabIds.includes(id));
        const previousTabId = history.length > 0 ? history[history.length - 1] : nextOpenTabIds[0];
        setActiveTabId(previousTabId);
      }

      tabHistoryRef.current = tabHistoryRef.current.filter((id) => id !== tabId);
    },
    [openTabIds, activeTabId],
  );

  const handleReorder = useCallback((newOrder: Array<string>): void => {
    setOpenTabIds(newOrder);
  }, []);

  const handleAddTab = useCallback((tabId: string): void => {
    setOpenTabIds((prev) => [...prev, tabId]);
    tabHistoryRef.current = [...tabHistoryRef.current, tabId];
    setActiveTabId(tabId);
  }, []);

  const handleTabListSelect = useCallback(
    (tabId: string): void => {
      if (openTabIds.includes(tabId)) {
        handleActivate(tabId);
      } else {
        handleAddTab(tabId);
      }
    },
    [openTabIds, handleActivate, handleAddTab],
  );

  const closedTabs = ALL_TABS.filter((t) => !openTabIds.includes(t.id));

  return (
    <div style={{ width: "100%", height: "400px", border: "1px solid var(--gray-a5)" }}>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      <TabBar
        tabs={[...ALL_TABS]}
        openTabIds={openTabIds}
        activeTabId={activeTabId}
        onActivate={handleActivate}
        onClose={handleClose}
        onReorder={handleReorder}
      >
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            <button
              type="button"
              disabled={closedTabs.length === 0}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 28,
                height: 28,
                border: "none",
                background: "transparent",
                color: closedTabs.length === 0 ? "var(--gray-a6)" : "var(--gray-a11)",
                cursor: closedTabs.length === 0 ? "default" : "pointer",
                borderRadius: 4,
              }}
            >
              <Plus width={14} height={14} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content>
            {closedTabs.length === 0 ? (
              <DropdownMenu.Item disabled>All tabs open</DropdownMenu.Item>
            ) : (
              closedTabs.map((tab) => (
                <DropdownMenu.Item key={tab.id} onSelect={() => handleAddTab(tab.id)}>
                  {tab.icon && (
                    <span style={{ display: "flex", alignItems: "center", marginRight: 4 }}>{tab.icon}</span>
                  )}
                  {tab.label}
                </DropdownMenu.Item>
              ))
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Root>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            <button
              type="button"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 28,
                height: 28,
                border: "none",
                background: "transparent",
                color: "var(--gray-a11)",
                cursor: "pointer",
                borderRadius: 4,
              }}
            >
              <MoreVertical width={14} height={14} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content>
            {ALL_TABS.map((tab) => (
              <DropdownMenu.Item key={tab.id} onSelect={() => handleTabListSelect(tab.id)}>
                <span style={{ display: "flex", alignItems: "center", gap: 4, width: "100%" }}>
                  {tab.icon && <span style={{ display: "flex", alignItems: "center" }}>{tab.icon}</span>}
                  <span style={{ flex: 1 }}>{tab.label}</span>
                  {openTabIds.includes(tab.id) && (
                    <span style={{ fontSize: 10, color: "var(--accent-9)" }}>&#10003;</span>
                  )}
                </span>
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </TabBar>
    </div>
  );
};

const meta = {
  title: "Custom/Tabs/TabBar",
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => <TabBarDemo />,
};

// --- Compact variant ---

const StatusDot = ({ color }: { color: string }): ReactElement => (
  <span
    style={{
      backgroundColor: color,
      borderRadius: "50%",
      flexShrink: 0,
      height: 6,
      width: 6,
    }}
  />
);

const COMPACT_TABS: ReadonlyArray<TabDefinition> = [
  { id: "src/app.tsx", label: "app.tsx", icon: <StatusDot color="var(--amber-11)" /> },
  { id: "src/utils/auth.ts", label: "auth.ts", icon: <StatusDot color="var(--green-11)" /> },
  { id: "src/components/Header.tsx", label: "Header.tsx", icon: <StatusDot color="var(--amber-11)" /> },
  { id: "README.md", label: "README.md", icon: <StatusDot color="var(--red-11)" /> },
  { id: "src/api/client.ts", label: "client.ts", icon: <StatusDot color="var(--purple-11)" /> },
];

const COMPACT_DEFAULT_OPEN = COMPACT_TABS.map((t) => t.id);

const CompactTabBarDemo = (): ReactElement => {
  const [openTabIds, setOpenTabIds] = useState<Array<string>>(COMPACT_DEFAULT_OPEN);
  const [activeTabId, setActiveTabId] = useState<string>(COMPACT_TABS[0].id);
  const tabHistoryRef = useRef<Array<string>>([COMPACT_TABS[0].id]);

  const handleActivate = useCallback((tabId: string): void => {
    tabHistoryRef.current = [...tabHistoryRef.current, tabId];
    setActiveTabId(tabId);
  }, []);

  const handleClose = useCallback(
    (tabId: string): void => {
      const nextOpenTabIds = openTabIds.filter((id) => id !== tabId);
      if (nextOpenTabIds.length === 0) return;

      setOpenTabIds(nextOpenTabIds);

      if (tabId === activeTabId) {
        const history = tabHistoryRef.current.filter((id) => id !== tabId && nextOpenTabIds.includes(id));
        const previousTabId = history.length > 0 ? history[history.length - 1] : nextOpenTabIds[0];
        setActiveTabId(previousTabId);
      }

      tabHistoryRef.current = tabHistoryRef.current.filter((id) => id !== tabId);
    },
    [openTabIds, activeTabId],
  );

  const handleReorder = useCallback((newOrder: Array<string>): void => {
    setOpenTabIds(newOrder);
  }, []);

  return (
    <div style={{ width: "100%", border: "1px solid var(--gray-a5)" }}>
      <TabBar
        tabs={[...COMPACT_TABS]}
        openTabIds={openTabIds}
        activeTabId={activeTabId}
        onActivate={handleActivate}
        onClose={handleClose}
        onReorder={handleReorder}
        variant="compact"
        alwaysCloseable
      >
        <Flex align="center" gap="2" style={{ borderLeft: "1px solid var(--gray-a5)", padding: "0 var(--space-2)" }}>
          <IconButton variant="ghost" size="1" color="gray">
            <Search size={14} />
          </IconButton>
          <IconButton variant="ghost" size="1" color="gray">
            <SplitSquareHorizontal size={14} />
          </IconButton>
          <IconButton variant="ghost" size="1" color="gray">
            <Maximize2 size={14} />
          </IconButton>
          <IconButton variant="ghost" size="1" color="gray">
            <X size={14} />
          </IconButton>
        </Flex>
      </TabBar>
    </div>
  );
};

export const Compact: Story = {
  render: () => <CompactTabBarDemo />,
};

// --- Terminal-style compact variant (children only, no rightContent) ---

const TerminalTabBarDemo = (): ReactElement => {
  const [nextIndex, setNextIndex] = useState(2);
  const [tabs, setTabs] = useState<Array<TabDefinition>>([
    { id: "term-1", label: "Terminal 1", icon: <StatusDot color="var(--green-11)" /> },
  ]);
  const [openTabIds, setOpenTabIds] = useState<Array<string>>(["term-1"]);
  const [activeTabId, setActiveTabId] = useState("term-1");

  const handleActivate = useCallback((tabId: string): void => {
    setActiveTabId(tabId);
  }, []);

  const handleClose = useCallback(
    (tabId: string): void => {
      const next = openTabIds.filter((id) => id !== tabId);
      if (next.length === 0) return;
      setOpenTabIds(next);
      setTabs((prev) => prev.filter((t) => t.id !== tabId));
      if (tabId === activeTabId) setActiveTabId(next[next.length - 1]);
    },
    [openTabIds, activeTabId],
  );

  const handleAdd = useCallback((): void => {
    const id = `term-${nextIndex}`;
    const newTab: TabDefinition = {
      id,
      label: `Terminal ${nextIndex}`,
      icon: <StatusDot color="var(--green-11)" />,
    };
    setTabs((prev) => [...prev, newTab]);
    setOpenTabIds((prev) => [...prev, id]);
    setActiveTabId(id);
    setNextIndex((n) => n + 1);
  }, [nextIndex]);

  const handleReorder = useCallback((newOrder: Array<string>): void => {
    setOpenTabIds(newOrder);
  }, []);

  return (
    <div style={{ width: "100%", border: "1px solid var(--gray-a5)" }}>
      <TabBar
        tabs={tabs}
        openTabIds={openTabIds}
        activeTabId={activeTabId}
        onActivate={handleActivate}
        onClose={handleClose}
        onReorder={handleReorder}
        variant="compact"
        alwaysCloseable
      >
        <IconButton variant="ghost" size="1" color="gray" onClick={handleAdd} aria-label="Add terminal">
          <Plus size={14} />
        </IconButton>
      </TabBar>
    </div>
  );
};

export const CompactTerminal: Story = {
  render: () => <TerminalTabBarDemo />,
};

// --- Diff-panel-style compact variant (children + rightContent) ---

const DIFF_FILE_NAMES = [
  "utils.ts",
  "Header.tsx",
  "README.md",
  "client.ts",
  "auth.ts",
  "config.json",
  "index.tsx",
  "styles.scss",
  "router.tsx",
];

const DiffTabBarDemo = (): ReactElement => {
  const [nextIndex, setNextIndex] = useState(2);
  const [tabs, setTabs] = useState<Array<TabDefinition>>([
    { id: "file-1", label: "app.tsx", icon: <StatusDot color="var(--amber-11)" /> },
  ]);
  const [openTabIds, setOpenTabIds] = useState<Array<string>>(["file-1"]);
  const [activeTabId, setActiveTabId] = useState("file-1");

  const handleActivate = useCallback((tabId: string): void => {
    setActiveTabId(tabId);
  }, []);

  const handleClose = useCallback(
    (tabId: string): void => {
      const next = openTabIds.filter((id) => id !== tabId);
      if (next.length === 0) return;
      setOpenTabIds(next);
      setTabs((prev) => prev.filter((t) => t.id !== tabId));
      if (tabId === activeTabId) setActiveTabId(next[next.length - 1]);
    },
    [openTabIds, activeTabId],
  );

  const handleAdd = useCallback((): void => {
    const id = `file-${nextIndex}`;
    const name = DIFF_FILE_NAMES[(nextIndex - 2) % DIFF_FILE_NAMES.length];
    const newTab: TabDefinition = {
      id,
      label: name,
      icon: <StatusDot color="var(--amber-11)" />,
    };
    setTabs((prev) => [...prev, newTab]);
    setOpenTabIds((prev) => [...prev, id]);
    setActiveTabId(id);
    setNextIndex((n) => n + 1);
  }, [nextIndex]);

  const handleReorder = useCallback((newOrder: Array<string>): void => {
    setOpenTabIds(newOrder);
  }, []);

  return (
    <Flex direction="column" gap="2">
      <div style={{ width: "100%", border: "1px solid var(--gray-a5)" }}>
        <TabBar
          tabs={tabs}
          openTabIds={openTabIds}
          activeTabId={activeTabId}
          onActivate={handleActivate}
          onClose={handleClose}
          onReorder={handleReorder}
          variant="compact"
          alwaysCloseable
          rightContent={
            <Flex align="center" gap="2" flexShrink="0">
              <IconButton variant="ghost" size="1" color="gray">
                <Columns2 size={14} />
              </IconButton>
              <IconButton variant="ghost" size="1" color="gray">
                <Maximize2 size={14} />
              </IconButton>
              <IconButton variant="ghost" size="1" color="gray">
                <X size={14} />
              </IconButton>
            </Flex>
          }
        >
          <Flex align="center" gap="2" flexShrink="0">
            <IconButton variant="ghost" size="1" color="gray">
              <Search size={14} />
            </IconButton>
            <IconButton variant="ghost" size="1" color="gray">
              <SplitSquareHorizontal size={14} />
            </IconButton>
            <IconButton variant="ghost" size="1" color="gray">
              <WrapText size={14} />
            </IconButton>
          </Flex>
        </TabBar>
      </div>
      <IconButton variant="soft" size="1" color="gray" onClick={handleAdd} aria-label="Add file tab">
        <Plus size={14} />
      </IconButton>
    </Flex>
  );
};

export const CompactDiffPanel: Story = {
  render: () => <DiffTabBarDemo />,
};
