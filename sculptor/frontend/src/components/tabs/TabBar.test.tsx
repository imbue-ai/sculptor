import { cleanup, fireEvent, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/components/panels/testUtils";
import { TabBar } from "~/components/tabs/TabBar";
import type { TabBarProps, TabDefinition } from "~/components/tabs/types";

const SAMPLE_TABS: Array<TabDefinition> = [
  { id: "tab-1", label: "Home", content: <div>Home content</div> },
  { id: "tab-2", label: "Settings", content: <div>Settings content</div> },
  { id: "tab-3", label: "Documents", content: <div>Documents content</div> },
  { id: "tab-4", label: "Terminal", content: <div>Terminal content</div> },
  {
    id: "tab-5",
    label: "Activity with a very long label that should show ellipsis when the tab is narrow enough",
    content: <div>Activity content</div>,
  },
];

const DEFAULT_PROPS: TabBarProps = {
  tabs: SAMPLE_TABS,
  openTabIds: ["tab-1", "tab-2", "tab-3"],
  activeTabId: "tab-1",
  onActivate: vi.fn(),
  onClose: vi.fn(),
  onReorder: vi.fn(),
};

const renderTabBar = (overrides: Partial<TabBarProps> = {}): ReturnType<typeof renderWithProviders> => {
  const store = createStore();
  const props = { ...DEFAULT_PROPS, ...overrides };
  return renderWithProviders(<TabBar {...props} />, store);
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("tab switching", () => {
  it("calls onActivate with the clicked tab id", () => {
    const onActivate = vi.fn();
    const { container } = renderTabBar({ onActivate });

    const secondTab = container.querySelector('[data-tab-id="tab-2"]');
    expect(secondTab).toBeInTheDocument();
    fireEvent.click(secondTab!);

    expect(onActivate).toHaveBeenCalledWith("tab-2");
  });

  it("renders the active tab with aria-selected true", () => {
    const { container } = renderTabBar({ activeTabId: "tab-2" });

    const activeTab = container.querySelector('[data-tab-id="tab-2"]');
    expect(activeTab).toHaveAttribute("aria-selected", "true");

    const inactiveTab = container.querySelector('[data-tab-id="tab-1"]');
    expect(inactiveTab).toHaveAttribute("aria-selected", "false");
  });

  it("displays the active tab content in the content area", () => {
    renderTabBar({ activeTabId: "tab-2" });
    expect(screen.getByTestId("tab-content")).toHaveTextContent("Settings content");
  });
});

describe("close tab", () => {
  it("calls onClose with the correct tab id when close button is clicked", () => {
    const onClose = vi.fn();
    const onActivate = vi.fn();
    const { container } = renderTabBar({ onClose, onActivate });

    const tab = container.querySelector('[data-tab-id="tab-2"]')!;
    fireEvent.mouseEnter(tab);

    const closeButton = tab.querySelector(`[data-testid="${ElementIds.TAB_CLOSE_BUTTON}"]`);
    expect(closeButton).toBeInTheDocument();
    fireEvent.click(closeButton!);

    expect(onClose).toHaveBeenCalledWith("tab-2");
    expect(onActivate).not.toHaveBeenCalled();
  });
});

describe("minimum tab enforcement", () => {
  it("does not render close button when only one tab is open", () => {
    const { container } = renderTabBar({ openTabIds: ["tab-1"] });

    const tab = container.querySelector('[data-tab-id="tab-1"]')!;
    fireEvent.mouseEnter(tab);

    const closeButton = tab.querySelector(`[data-testid="${ElementIds.TAB_CLOSE_BUTTON}"]`);
    expect(closeButton).not.toBeInTheDocument();
  });
});

describe("drag and drop reorder", () => {
  it("renders tabs in the sortable context with correct order", () => {
    const { container } = renderTabBar();

    const tabs = container.querySelectorAll('[role="tab"]');
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveAttribute("data-tab-id", "tab-1");
    expect(tabs[1]).toHaveAttribute("data-tab-id", "tab-2");
    expect(tabs[2]).toHaveAttribute("data-tab-id", "tab-3");
  });
});

describe("text overflow", () => {
  it("applies ellipsis class to the label element", () => {
    const { container } = renderTabBar({
      openTabIds: ["tab-5"],
      activeTabId: "tab-5",
    });

    const tab = container.querySelector('[data-tab-id="tab-5"]')!;
    const label = tab.querySelector(".label");
    expect(label).toBeInTheDocument();
    expect(label).toHaveClass("label");
  });
});

describe("hover states", () => {
  it("shows close button on hover and removes it on leave", () => {
    const { container } = renderTabBar();

    const tab = container.querySelector('[data-tab-id="tab-2"]')!;

    expect(tab.querySelector(`[data-testid="${ElementIds.TAB_CLOSE_BUTTON}"]`)).not.toBeInTheDocument();

    fireEvent.mouseEnter(tab);
    expect(tab.querySelector(`[data-testid="${ElementIds.TAB_CLOSE_BUTTON}"]`)).toBeInTheDocument();
    expect(tab).toHaveClass("hovered");

    fireEvent.mouseLeave(tab);
    expect(tab.querySelector(`[data-testid="${ElementIds.TAB_CLOSE_BUTTON}"]`)).not.toBeInTheDocument();
    expect(tab).not.toHaveClass("hovered");
  });

  it("shows close button on active tab without hover", () => {
    const { container } = renderTabBar({ activeTabId: "tab-1" });

    const activeTab = container.querySelector('[data-tab-id="tab-1"]')!;
    const closeButton = activeTab.querySelector(`[data-testid="${ElementIds.TAB_CLOSE_BUTTON}"]`);
    expect(closeButton).toBeInTheDocument();
  });
});

describe("long hover preview", () => {
  it("renders with HoverCard when preview content is defined", () => {
    const tabsWithPreview: Array<TabDefinition> = [
      { id: "tab-1", label: "Home", content: <div>Home content</div>, preview: <div>Home preview</div> },
      { id: "tab-2", label: "Settings", content: <div>Settings content</div> },
    ];

    const { container } = renderTabBar({
      tabs: tabsWithPreview,
      openTabIds: ["tab-1", "tab-2"],
      activeTabId: "tab-1",
    });

    const tab = container.querySelector('[data-tab-id="tab-1"]');
    expect(tab).toBeInTheDocument();
  });
});

describe("all open tabs rendered", () => {
  it("renders all open tabs in the scrollable container", () => {
    const { container } = renderTabBar({
      openTabIds: ["tab-1", "tab-2", "tab-3"],
    });

    const tabs = container.querySelectorAll('[role="tab"]');
    expect(tabs).toHaveLength(3);
  });
});

describe("ARIA attributes", () => {
  it("renders the tab bar with role tablist", () => {
    renderTabBar();
    expect(screen.getByRole("tablist")).toBeInTheDocument();
  });

  it("renders the content area with role tabpanel", () => {
    renderTabBar();
    expect(screen.getByTestId("tab-content")).toBeInTheDocument();
  });

  it("only renders open tabs, not the full pool", () => {
    const { container } = renderTabBar({
      openTabIds: ["tab-1", "tab-3"],
    });

    const tabs = container.querySelectorAll('[role="tab"]');
    expect(tabs).toHaveLength(2);
    expect(container.querySelector('[data-tab-id="tab-2"]')).not.toBeInTheDocument();
  });

  it("preserves openTabIds order", () => {
    const { container } = renderTabBar({
      openTabIds: ["tab-3", "tab-1", "tab-2"],
    });

    const tabs = container.querySelectorAll('[role="tab"]');
    expect(tabs[0]).toHaveAttribute("data-tab-id", "tab-3");
    expect(tabs[1]).toHaveAttribute("data-tab-id", "tab-1");
    expect(tabs[2]).toHaveAttribute("data-tab-id", "tab-2");
  });

  it("all tabs have uniform width", () => {
    const { container } = renderTabBar();

    const tabs = container.querySelectorAll('[role="tab"]');
    const widths = Array.from(tabs).map((tab) => (tab as HTMLElement).style.width);
    const uniqueWidths = new Set(widths);
    expect(uniqueWidths.size).toBe(1);
  });
});
