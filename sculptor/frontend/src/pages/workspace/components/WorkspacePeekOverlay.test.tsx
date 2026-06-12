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

const OPEN_DELAY_MS = 600;
const CLOSE_DELAY_MS = 80;
const REOPEN_GRACE_PERIOD_MS = 300;

/**
 * Creates a fake workspace tab element in the DOM for event delegation.
 */
const createTab = (workspaceId: string): HTMLElement => {
  const tab = document.createElement("div");
  tab.setAttribute("data-workspace-tab", "");
  tab.setAttribute("data-tab-id", workspaceId);
  tab.getBoundingClientRect = (): DOMRect => ({
    left: 100,
    right: 200,
    top: 0,
    bottom: 40,
    width: 100,
    height: 40,
    x: 100,
    y: 0,
    toJSON: (): string => "",
  });
  document.body.appendChild(tab);
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
  it("opens after OPEN_DELAY_MS on first hover", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const tab = createTab("ws-1");

    hoverTab(tab);

    // Not visible before delay
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));

    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });

  it("reopens immediately when re-entering within the grace period", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const tab = createTab("ws-1");

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

  it("requires full delay when re-entering after the grace period expires", () => {
    render(<WorkspacePeekOverlay onNavigate={vi.fn()} />);
    const tab = createTab("ws-1");

    // Open the popover
    hoverTab(tab);
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();

    // Leave tab and let it close
    leaveTab(tab);
    act(() => vi.advanceTimersByTime(CLOSE_DELAY_MS));
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    // Wait past the grace period
    act(() => vi.advanceTimersByTime(REOPEN_GRACE_PERIOD_MS + 100));

    // Re-enter — should NOT open immediately
    hoverTab(tab);
    act(() => vi.advanceTimersByTime(0));
    expect(screen.queryByTestId("workspace-peek-overlay")).toBeNull();

    // Should open after full delay
    act(() => vi.advanceTimersByTime(OPEN_DELAY_MS));
    expect(screen.getByTestId("workspace-peek-overlay")).toBeDefined();
  });
});
