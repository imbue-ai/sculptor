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
 * Creates a workspace-peek "tab" row nested inside a sidebar container, mirroring
 * the real DOM shape:
 *   aside[data-testid=WORKSPACE_SIDEBAR] > div[data-workspace-tab] > (name button + action button)
 * The peek attributes live on the row container (not the name button) so the
 * whole row — including its sibling hover-action buttons — counts as one tab.
 * The row's right edge is intentionally inset from the sidebar's right edge.
 */
const createSidebarTab = (workspaceId: string): { nameButton: HTMLElement; actionButton: HTMLElement } => {
  const sidebar = document.createElement("aside");
  sidebar.setAttribute("data-testid", "WORKSPACE_SIDEBAR");
  sidebar.getBoundingClientRect = (): DOMRect =>
    mockRect({ left: 0, right: SIDEBAR_RIGHT, top: SIDEBAR_TOP, bottom: 600, width: SIDEBAR_RIGHT, height: 600 });

  const row = document.createElement("div");
  row.setAttribute("data-workspace-tab", "");
  row.setAttribute("data-tab-id", workspaceId);
  row.getBoundingClientRect = (): DOMRect =>
    mockRect({ left: 20, right: ROW_RIGHT, top: ROW_TOP, bottom: ROW_TOP + 28, width: ROW_RIGHT - 20, height: 28 });

  // The clickable name button and the hover-revealed action button (menu/delete)
  // are siblings inside the row; neither carries the peek attributes itself.
  const nameButton = document.createElement("button");
  const actionButton = document.createElement("button");
  row.appendChild(nameButton);
  row.appendChild(actionButton);

  sidebar.appendChild(row);
  document.body.appendChild(sidebar);
  return { nameButton, actionButton };
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
    const { nameButton } = createSidebarTab("ws-1");

    hoverTab(nameButton);

    // Not visible until the (0ms) open timer flushes on the next tick.
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));

    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });

  it("reopens instantly after closing", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const { nameButton } = createSidebarTab("ws-1");

    // Open the popover
    hoverTab(nameButton);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();

    // Leave tab and let it close
    leaveTab(nameButton);
    act(() => vi.advanceTimersByTime(CLOSE_DELAY_MS));
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    // Re-enter — the peek has no open delay, so it appears instantly again.
    hoverTab(nameButton);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });

  it("stays open when moving from the name button onto a sibling hover-action button", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const { nameButton, actionButton } = createSidebarTab("ws-1");

    hoverTab(nameButton);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();

    // Moving from the name button onto the row's menu/delete button is NOT
    // leaving the tab: both live inside the same [data-workspace-tab] row, so
    // the peek must stay open. (Regression: it used to close because the action
    // buttons sat outside the tab element that carried the peek attributes.)
    const event = new MouseEvent("mouseout", { bubbles: true });
    Object.defineProperty(event, "target", { value: nameButton });
    Object.defineProperty(event, "relatedTarget", { value: actionButton });
    document.dispatchEvent(event);

    act(() => vi.advanceTimersByTime(CLOSE_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });

  it("anchors to the sidebar's right edge, not the (variable) row width", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const { nameButton } = createSidebarTab("ws-1");

    hoverTab(nameButton);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));

    const overlay = screen.getByTestId("workspace-peek-overlay");
    // The peek must sit flush against the sidebar edge regardless of how wide the
    // row is (the row's right edge shifts as hover-action icons appear/hide).
    expect(overlay.style.transform).toBe(`translate(${SIDEBAR_RIGHT + PEEK_OFFSET_PX}px, ${ROW_TOP}px)`);
    // Explicitly reject anchoring to the row's inset right edge.
    expect(overlay.style.transform).not.toContain(`${ROW_RIGHT + PEEK_OFFSET_PX}px`);
  });
});
