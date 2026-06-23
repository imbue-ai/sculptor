import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { Circle } from "lucide-react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";
import { createPanelStore, zoneVisibilityAtom } from "~/components/panels/atoms.ts";
import { renderWithProviders } from "~/components/panels/testUtils";
import type { PanelDefinition } from "~/components/panels/types.ts";

import { BottomBar } from "./BottomBar";

const TEST_PANELS: ReadonlyArray<PanelDefinition> = [
  {
    id: "info",
    displayName: "Info",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: () => createElement("div", null, "INFO"),
  },
  {
    id: "terminal",
    displayName: "Terminal",
    description: "Test panel",
    icon: Circle,
    defaultZone: "bottom",
    defaultShortcut: "",
    component: () => createElement("div", null, "TERMINAL"),
  },
  {
    id: "changes",
    displayName: "Changes",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: () => createElement("div", null, "CHANGES"),
  },
];

const createDefaultStore = (): ReturnType<typeof createPanelStore> =>
  createPanelStore(TEST_PANELS, { useDefaultLayout: true });

beforeEach(() => localStorage.clear());
afterEach(cleanup);

describe("BottomBar", () => {
  it("renders three side toggle buttons", () => {
    const store = createDefaultStore();
    renderWithProviders(<BottomBar />, { store, panels: TEST_PANELS });

    expect(screen.getByTestId(ElementIds.SIDE_TOGGLE_LEFT)).toBeInTheDocument();
    expect(screen.getByTestId(ElementIds.SIDE_TOGGLE_BOTTOM)).toBeInTheDocument();
    expect(screen.getByTestId(ElementIds.SIDE_TOGGLE_RIGHT)).toBeInTheDocument();
  });

  it("toggle button has active styling when side is visible", () => {
    const store = createDefaultStore();
    renderWithProviders(<BottomBar />, { store, panels: TEST_PANELS });

    const rightBtn = screen.getByTestId(ElementIds.SIDE_TOGGLE_RIGHT);
    // The right side is visible by default (changes panel in top-right)
    expect(rightBtn.className).toContain("toggleActive");
  });

  it("toggle button has inactive styling when side is hidden", () => {
    const store = createDefaultStore();
    store.set(zoneVisibilityAtom, (prev) => ({
      ...prev,
      "top-right": false,
      "bottom-right": false,
    }));
    renderWithProviders(<BottomBar />, { store, panels: TEST_PANELS });

    const rightBtn = screen.getByTestId(ElementIds.SIDE_TOGGLE_RIGHT);
    expect(rightBtn.className).toContain("toggleInactive");
  });

  it("clicking a toggle button hides the corresponding side", () => {
    const store = createDefaultStore();
    renderWithProviders(<BottomBar />, { store, panels: TEST_PANELS });

    const rightBtn = screen.getByTestId(ElementIds.SIDE_TOGGLE_RIGHT);
    act(() => fireEvent.click(rightBtn));

    const vis = store.get(zoneVisibilityAtom);
    expect(vis["top-right"]).toBe(false);
  });

  it("clicking a toggle button twice restores visibility", () => {
    const store = createDefaultStore();
    renderWithProviders(<BottomBar />, { store, panels: TEST_PANELS });

    const rightBtn = screen.getByTestId(ElementIds.SIDE_TOGGLE_RIGHT);
    act(() => fireEvent.click(rightBtn)); // hide
    act(() => fireEvent.click(rightBtn)); // restore

    const vis = store.get(zoneVisibilityAtom);
    expect(vis["top-right"]).toBe(true);
  });

  it("side toggle is aria-disabled only when its side has no panels", () => {
    // Registry with no left-side panel — `info` (top-left) is dropped, so the
    // left side is empty while bottom and right still have panels.
    const sidePanels = TEST_PANELS.slice(1);
    const store = createPanelStore(sidePanels, { useDefaultLayout: true });
    renderWithProviders(<BottomBar />, { store, panels: sidePanels });

    // An empty side is disabled in the DOM, not just styled.
    expect(screen.getByTestId(ElementIds.SIDE_TOGGLE_LEFT).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByTestId(ElementIds.SIDE_TOGGLE_RIGHT).getAttribute("aria-disabled")).toBe("false");
  });
});
