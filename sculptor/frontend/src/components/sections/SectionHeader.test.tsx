import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
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

  it("does not add maximized top padding when the section is not maximized", () => {
    const store = storeWith(false);
    renderWithProviders(<SectionHeader subSection="center" />, { store });

    const header = screen.getByTestId(`${ElementIds.SECTION_HEADER}-center`);
    expect(header.getAttribute("data-maximized")).toBeNull();
  });

  it("adds top padding so the tab strip clears the OS window controls when maximized", () => {
    const store = storeWith(true);
    renderWithProviders(<SectionHeader subSection="center" />, { store });

    const header = screen.getByTestId(`${ElementIds.SECTION_HEADER}-center`);
    expect(header.getAttribute("data-maximized")).toBe("true");
  });
});
