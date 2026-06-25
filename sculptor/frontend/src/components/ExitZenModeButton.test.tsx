import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { Circle } from "lucide-react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { createPanelStore, zenModeActiveAtom } from "~/components/panels/atoms.ts";
import { renderWithProviders } from "~/components/panels/testUtils";
import type { PanelDefinition } from "~/components/panels/types.ts";

import { ExitZenModeButton } from "./ExitZenModeButton";

vi.mock("~/common/keybindings/hooks.ts", () => ({
  useKeybindingDisplayText: vi.fn(() => "MOCK_SHORTCUT"),
}));

const TEST_PANELS: ReadonlyArray<PanelDefinition> = [
  {
    id: "info",
    displayName: "Info",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
  {
    id: "cost",
    displayName: "Cost",
    description: "Test panel",
    icon: Circle,
    defaultZone: "bottom-left",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
  {
    id: "terminal",
    displayName: "Terminal",
    description: "Test panel",
    icon: Circle,
    defaultZone: "bottom",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
  {
    id: "changes",
    displayName: "Changes",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
];

const renderInZenMode = (): ReturnType<typeof renderWithProviders> => {
  const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
  act(() => store.set(zenModeActiveAtom, true));
  return renderWithProviders(<ExitZenModeButton />, { store, panels: TEST_PANELS });
};

const getHotZone = (): HTMLElement => {
  // The hot zone is the outermost div rendered by the component.
  const testIdElement = screen.getByTestId(ElementIds.EXIT_ZEN_MODE_BUTTON);
  return testIdElement.parentElement!;
};

const getButtonContainer = (): HTMLElement => screen.getByTestId(ElementIds.EXIT_ZEN_MODE_BUTTON);

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  localStorage.clear();
});

describe("ExitZenModeButton", () => {
  it("returns null when zen mode is inactive", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    renderWithProviders(<ExitZenModeButton />, { store, panels: TEST_PANELS });

    expect(screen.queryByTestId(ElementIds.EXIT_ZEN_MODE_BUTTON)).not.toBeInTheDocument();
  });

  it("renders hot zone when zen mode is active", () => {
    renderInZenMode();
    const hotZone = getHotZone();

    expect(hotZone).toBeInTheDocument();
  });

  it("button starts hidden", () => {
    renderInZenMode();
    const buttonContainer = getButtonContainer();

    expect(buttonContainer.className).not.toContain("visible");
  });

  it("shows button on mouse enter", () => {
    renderInZenMode();
    const hotZone = getHotZone();

    fireEvent.mouseEnter(hotZone);

    const buttonContainer = getButtonContainer();
    expect(buttonContainer.className).toContain("visible");
  });

  it("hides button after mouse leave", () => {
    renderInZenMode();
    const hotZone = getHotZone();

    fireEvent.mouseEnter(hotZone);
    fireEvent.mouseLeave(hotZone);

    act(() => vi.advanceTimersByTime(150));

    const buttonContainer = getButtonContainer();
    expect(buttonContainer.className).not.toContain("visible");
  });

  it("re-entering before timeout cancels hide", () => {
    renderInZenMode();
    const hotZone = getHotZone();

    fireEvent.mouseEnter(hotZone);
    fireEvent.mouseLeave(hotZone);
    // Re-enter before the 150ms timeout fires.
    fireEvent.mouseEnter(hotZone);

    act(() => vi.advanceTimersByTime(150));

    const buttonContainer = getButtonContainer();
    expect(buttonContainer.className).toContain("visible");
  });

  it("clicking button calls toggleZenMode", () => {
    const { store } = renderInZenMode();
    const hotZone = getButtonContainer().parentElement!;

    // Reveal the button first.
    fireEvent.mouseEnter(hotZone);

    const button = screen.getByRole("button", { name: /exit zen mode/i });
    fireEvent.click(button);

    expect(store.get(zenModeActiveAtom)).toBe(false);
  });

  // Regression: the shortcut shown in the button must come from the user's
  // keybinding (useKeybindingDisplayText("zen_mode")), not a hardcoded literal.
  // The mocked hook returns "MOCK_SHORTCUT"; a hardcoded literal would not.
  it("renders the shortcut from the keybinding hook", () => {
    renderInZenMode();
    const hotZone = getButtonContainer().parentElement!;
    fireEvent.mouseEnter(hotZone);

    const button = screen.getByRole("button", { name: /exit zen mode/i });
    expect(button.textContent).toContain("MOCK_SHORTCUT");
  });
});
