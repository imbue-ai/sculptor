import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";
import { DEFAULT_THEME_BUILDER_SETTINGS, themeBuilderSettingsAtom } from "~/common/state/atoms/themeBuilder.ts";

import { ThemeBuilderSection } from "./ThemeBuilderSection";

type Store = ReturnType<typeof createStore>;

const createWrapper =
  (store: Store) =>
  ({ children }: { children: ReactNode }): ReactElement => (
    <MemoryRouter>
      <Provider store={store}>
        <Theme>{children}</Theme>
      </Provider>
    </MemoryRouter>
  );

beforeEach(() => localStorage.clear());
afterEach(cleanup);

describe("ThemeBuilderSection", () => {
  describe("rendering", () => {
    it("renders all setting row titles", () => {
      const store = createStore();
      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      const expectedTitles = [
        "Appearance",
        "Accent color",
        "Gray color",
        "Radius",
        "Scaling",
        "Panel background",
        "Danger color",
        "Success color",
        "Warning color",
        "Info color",
      ];

      for (const title of expectedTitles) {
        expect(screen.getByText(title)).toBeInTheDocument();
      }
    });

    it("renders the reset button", () => {
      const store = createStore();
      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      expect(screen.getByTestId(ElementIds.SETTINGS_THEME_BUILDER_RESET)).toBeInTheDocument();
      expect(screen.getByText("Reset to defaults")).toBeInTheDocument();
    });

    it("renders all setting controls with test IDs", () => {
      const store = createStore();
      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      const testIds = [
        ElementIds.SETTINGS_THEME_BUILDER_ACCENT_COLOR,
        ElementIds.SETTINGS_THEME_BUILDER_GRAY_COLOR,
        ElementIds.SETTINGS_THEME_BUILDER_APPEARANCE,
        ElementIds.SETTINGS_THEME_BUILDER_RADIUS,
        ElementIds.SETTINGS_THEME_BUILDER_SCALING,
        ElementIds.SETTINGS_THEME_BUILDER_PANEL_BACKGROUND,
        ElementIds.SETTINGS_THEME_BUILDER_DANGER_COLOR,
        ElementIds.SETTINGS_THEME_BUILDER_SUCCESS_COLOR,
        ElementIds.SETTINGS_THEME_BUILDER_WARNING_COLOR,
        ElementIds.SETTINGS_THEME_BUILDER_INFO_COLOR,
      ];

      for (const testId of testIds) {
        expect(screen.getByTestId(testId)).toBeInTheDocument();
      }
    });
  });

  describe("default values", () => {
    it("shows default accent color as selected swatch", () => {
      const store = createStore();
      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      const grid = screen.getByTestId(ElementIds.SETTINGS_THEME_BUILDER_ACCENT_COLOR);
      const selectedSwatch = within(grid).getByRole("radio", { checked: true });
      expect(selectedSwatch).toHaveAttribute("aria-label", DEFAULT_THEME_BUILDER_SETTINGS.accentColor);
    });

    it("shows default danger color as selected swatch", () => {
      const store = createStore();
      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      const grid = screen.getByTestId(ElementIds.SETTINGS_THEME_BUILDER_DANGER_COLOR);
      const selectedSwatch = within(grid).getByRole("radio", { checked: true });
      expect(selectedSwatch).toHaveAttribute("aria-label", DEFAULT_THEME_BUILDER_SETTINGS.dangerColor);
    });

    it("shows default radius as selected preview", () => {
      const store = createStore();
      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      const grid = screen.getByTestId(ElementIds.SETTINGS_THEME_BUILDER_RADIUS);
      const selectedPreview = within(grid).getByRole("radio", { checked: true });
      expect(selectedPreview).toHaveAttribute("aria-label", DEFAULT_THEME_BUILDER_SETTINGS.radius);
    });
  });

  describe("selected value labels", () => {
    it("displays selected color names as text labels", () => {
      const store = createStore();
      store.set(themeBuilderSettingsAtom, {
        ...DEFAULT_THEME_BUILDER_SETTINGS,
        accentColor: "blue",
        dangerColor: "crimson",
      });

      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      expect(screen.getByText("blue")).toBeInTheDocument();
      expect(screen.getByText("crimson")).toBeInTheDocument();
    });
  });

  describe("custom initial state", () => {
    it("reflects custom settings from the atom", () => {
      const store = createStore();
      store.set(themeBuilderSettingsAtom, {
        ...DEFAULT_THEME_BUILDER_SETTINGS,
        accentColor: "blue",
        dangerColor: "crimson",
      });

      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      const accentGrid = screen.getByTestId(ElementIds.SETTINGS_THEME_BUILDER_ACCENT_COLOR);
      const selectedAccent = within(accentGrid).getByRole("radio", { checked: true });
      expect(selectedAccent).toHaveAttribute("aria-label", "blue");

      const dangerGrid = screen.getByTestId(ElementIds.SETTINGS_THEME_BUILDER_DANGER_COLOR);
      const selectedDanger = within(dangerGrid).getByRole("radio", { checked: true });
      expect(selectedDanger).toHaveAttribute("aria-label", "crimson");
    });
  });

  describe("reset to defaults", () => {
    it("preserves appearance setting when resetting to defaults", () => {
      const store = createStore();
      store.set(themeBuilderSettingsAtom, {
        ...DEFAULT_THEME_BUILDER_SETTINGS,
        appearance: "dark",
        accentColor: "blue",
      });

      render(<ThemeBuilderSection />, { wrapper: createWrapper(store) });

      fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_THEME_BUILDER_RESET));

      const currentSettings = store.get(themeBuilderSettingsAtom);
      expect(currentSettings.appearance).toBe("dark");
      expect(currentSettings.accentColor).toBe(DEFAULT_THEME_BUILDER_SETTINGS.accentColor);
    });
  });
});
