import { act, cleanup, render, screen } from "@testing-library/react";
import type React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkspacePeekOverlay } from "./WorkspacePeekOverlay";

vi.mock("./WorkspacePeekPopover", () => ({
  WorkspacePeekPopover: ({ workspaceId }: { workspaceId: string }): React.ReactElement => (
    <div data-testid="workspace-peek-popover">{workspaceId}</div>
  ),
}));

vi.mock("./WorkspacePeekOverlay.module.scss", () => ({
  default: { overlay: "overlay", animated: "animated" },
}));

// The peek opens instantly (0ms) — kept as a named constant for the advance-timers calls.
const OPEN_DELAY_MS = 0;
const CLOSE_DELAY_MS = 80;
const REOPEN_GRACE_PERIOD_MS = 300;
const PEEK_OFFSET_PX = 4;

// The sidebar container the peek should anchor to. Its right edge is the stable
// reference point regardless of how wide the sidebar (or the row) is.
const SIDEBAR_RIGHT = 250;
const SIDEBAR_TOP = 0;
// The row button is inset from the sidebar edge (e.g. because hover-action
// icons occupy the trailing space), so its right edge is NOT the sidebar edge.
const ROW_RIGHT = 180;
const ROW_TOP = 40;

const mockRect = (over: Partial<DOMRect>): DOMRect => ({
  left: 0,
  right: 0,
  top: 0,
  bottom: 0,
  width: 0,
  height: 0,
  x: 0,
  y: 0,
  toJSON: (): string => "",
  ...over,
});

/**
 * Creates a workspace-tab row nested inside a sidebar container, mirroring the
 * real DOM shape (aside[data-testid=WORKSPACE_SIDEBAR] > button[data-workspace-tab]).
 * The row's right edge is intentionally inset from the sidebar's right edge.
 */
const createSidebarTab = (workspaceId: string): HTMLElement => {
  const sidebar = document.createElement("aside");
  sidebar.setAttribute("data-testid", "WORKSPACE_SIDEBAR");
  sidebar.getBoundingClientRect = (): DOMRect =>
    mockRect({ left: 0, right: SIDEBAR_RIGHT, top: SIDEBAR_TOP, bottom: 600, width: SIDEBAR_RIGHT, height: 600 });

  const tab = document.createElement("button");
  tab.setAttribute("data-workspace-tab", "");
  tab.setAttribute("data-tab-id", workspaceId);
  tab.getBoundingClientRect = (): DOMRect =>
    mockRect({ left: 20, right: ROW_RIGHT, top: ROW_TOP, bottom: ROW_TOP + 28, width: ROW_RIGHT - 20, height: 28 });

  sidebar.appendChild(tab);
  document.body.appendChild(sidebar);
  return tab;
};

const hoverTab = (tab: HTMLElement): void => {
  const event = new MouseEvent("mouseover", { bubbles: true });
  Object.defineProperty(event, "target", { value: tab });
  document.dispatchEvent(event);
};

const leaveTab = (tab: HTMLElement): void => {
  const event = new MouseEvent("mouseout", { bubbles: true });
  Object.defineProperty(event, "target", { value: tab });
  Object.defineProperty(event, "relatedTarget", { value: document.body });
  document.dispatchEvent(event);
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  document.body.innerHTML = "";
});

describe("WorkspacePeekOverlay", () => {
  it("opens instantly on hover", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const tab = createSidebarTab("ws-1");

    hoverTab(tab);

    // Not visible until the (0ms) open timer flushes on the next tick.
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));

    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });

  it("reopens immediately when re-entering within the grace period", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const tab = createSidebarTab("ws-1");

    // Open the popover
    hoverTab(tab);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();

    // Leave tab and let it close
    leaveTab(tab);
    act(() => vi.advanceTimersByTime(CLOSE_DELAY_MS));
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    // Re-enter within grace period — should open immediately (0ms delay)
    hoverTab(tab);
    act(() => vi.advanceTimersByTime(0));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });

  it("still opens instantly when re-entering after the grace period expires", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const tab = createSidebarTab("ws-1");

    // Open the popover
    hoverTab(tab);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();

    // Leave tab and let it close
    leaveTab(tab);
    act(() => vi.advanceTimersByTime(CLOSE_DELAY_MS));
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    // Wait past the grace period, then re-enter — the peek has no open delay, so it
    // still appears instantly rather than waiting.
    act(() => vi.advanceTimersByTime(REOPEN_GRACE_PERIOD_MS + 100));
    hoverTab(tab);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });

  it("anchors to the sidebar's right edge, not the (variable) row width", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const tab = createSidebarTab("ws-1");

    hoverTab(tab);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));

    const overlay = screen.getByTestId("workspace-peek-overlay");
    // The peek must sit flush against the sidebar edge regardless of how wide the
    // row is (the row's right edge shifts as hover-action icons appear/hide).
    expect(overlay.style.transform).toBe(`translate(${SIDEBAR_RIGHT + PEEK_OFFSET_PX}px, ${ROW_TOP}px)`);
    // Explicitly reject anchoring to the row's inset right edge.
    expect(overlay.style.transform).not.toContain(`${ROW_RIGHT + PEEK_OFFSET_PX}px`);
  });
});
