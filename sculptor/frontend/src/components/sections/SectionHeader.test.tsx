import { DndContext } from "@dnd-kit/core";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import { activePanelIdInSubSectionAtom, activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import { SectionHeader } from "./SectionHeader.tsx";
import { maximizedSectionAtom } from "./transientAtoms.ts";

// The add-panel dropdown pulls in the agent-type registrations + keybinding hooks
// (deep deps we don't need here). We only care about where its trigger button lands in
// the header, so render it as its bare trigger.
vi.mock("./AddPanelDropdown.tsx", () => ({
  AddPanelDropdown: ({ trigger }: { trigger: ReactElement }): ReactElement => trigger,
}));

afterEach(cleanup);

function storeWith(maximized: boolean): ReturnType<typeof createStore> {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, "ws-test");
  store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });
  if (maximized) {
    store.set(maximizedSectionAtom, "center");
  }
  return store;
}

describe("SectionHeader chrome layout", () => {
  it("left-aligns the add-panel button next to the tab strip, apart from the right-pinned maximize control", () => {
    const store = storeWith(false);
    renderWithProviders(<SectionHeader subSection="center" />, { store });

    const addButton = screen.getByTestId(`${ElementIds.SECTION_ADD_PANEL_BUTTON}-center`);
    const maximizeButton = screen.getByTestId(`${ElementIds.SECTION_MAXIMIZE_BUTTON}-center`);

    // Before the fix the "+" lived inside the same right-pinned controls group as the
    // maximize toggle; now it is a direct child of the header, ahead of that group.
    expect(addButton.parentElement).not.toBe(maximizeButton.parentElement);
    expect(addButton.compareDocumentPosition(maximizeButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("does not mark the header as maximized when the section is not maximized", () => {
    const store = storeWith(false);
    renderWithProviders(<SectionHeader subSection="center" />, { store });

    const header = screen.getByTestId(`${ElementIds.SECTION_HEADER}-center`);
    expect(header.getAttribute("data-maximized")).toBeNull();
  });

  it("marks the header as maximized when the section is maximized", () => {
    const store = storeWith(true);
    renderWithProviders(<SectionHeader subSection="center" />, { store });

    const header = screen.getByTestId(`${ElementIds.SECTION_HEADER}-center`);
    expect(header.getAttribute("data-maximized")).toBe("true");
  });
});

// Two static panels (from the registry's default static definitions) in the center
// strip, "files" active. Tabs are dnd-kit draggables, so they render inside a real
// DndContext with its default sensors — Space must stay the keyboard sensor's
// drag-pickup key while Enter activates the tab.
function storeWithTwoTabs(): ReturnType<typeof createStore> {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, "ws-test");
  store.set(workspaceLayoutAtom, {
    ...EMPTY_WORKSPACE_LAYOUT,
    placement: { files: "center", changes: "center" },
    order: { center: ["files", "changes"] },
    activePanel: { center: "files" },
  });
  return store;
}

function renderTwoTabs(onDragStart?: () => void): ReturnType<typeof createStore> {
  const store = storeWithTwoTabs();
  renderWithProviders(
    <DndContext onDragStart={onDragStart}>
      <SectionHeader subSection="center" />
    </DndContext>,
    { store },
  );
  return store;
}

describe("SectionHeader keyboard activation", () => {
  it("exposes the tab strip as a horizontal tablist of tabs", () => {
    renderTwoTabs();

    const tablist = screen.getByRole("tablist");
    expect(tablist).toHaveAttribute("aria-orientation", "horizontal");
    expect(screen.getAllByRole("tab")).toHaveLength(2);
  });

  it("activates a tab with Enter without starting a drag", () => {
    const onDragStart = vi.fn();
    const store = renderTwoTabs(onDragStart);

    const changesTab = screen.getByTestId(`${ElementIds.PANEL_TAB}-changes`);
    expect(changesTab).toHaveAttribute("aria-selected", "false");

    fireEvent.keyDown(changesTab, { key: "Enter", code: "Enter" });

    expect(store.get(activePanelIdInSubSectionAtom("center"))).toBe("changes");
    expect(screen.getByTestId(`${ElementIds.PANEL_TAB}-changes`)).toHaveAttribute("aria-selected", "true");
    expect(onDragStart).not.toHaveBeenCalled();
  });

  it("leaves Space to the drag sensor's pickup instead of activating the tab", () => {
    const onDragStart = vi.fn();
    const store = renderTwoTabs(onDragStart);

    const changesTab = screen.getByTestId(`${ElementIds.PANEL_TAB}-changes`);
    fireEvent.keyDown(changesTab, { key: " ", code: "Space" });

    // Space is the documented drag-pickup key (focus → Space → arrows → Space);
    // it must reach the keyboard sensor and must not double as activation.
    expect(onDragStart).toHaveBeenCalledTimes(1);
    expect(store.get(activePanelIdInSubSectionAtom("center"))).toBe("files");
  });

  it("does not hijack an Enter aimed at the tab's close button", () => {
    const store = renderTwoTabs();

    const closeButton = screen.getByTestId(`${ElementIds.PANEL_TAB_CLOSE}-changes`);
    fireEvent.keyDown(closeButton, { key: "Enter", code: "Enter" });

    // The keydown bubbles through the tab, but only keys targeted at the tab
    // itself may activate it — the button's native Enter-to-click stays intact.
    expect(store.get(activePanelIdInSubSectionAtom("center"))).toBe("files");
  });
});
