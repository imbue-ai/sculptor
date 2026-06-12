import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import {
  ACCENT_COLORS,
  DEFAULT_THEME_BUILDER_SETTINGS,
  GRAY_COLORS,
  PANEL_BACKGROUNDS,
  RADII,
  SCALINGS,
  themeAccentColorAtom,
  themeAppearanceAtom,
  themeBuilderSettingsAtom,
  themeDangerColorAtom,
  themeGrayColorAtom,
  themeSuccessColorAtom,
  themeWarningColorAtom,
} from "./themeBuilder";

describe("theme builder constants", () => {
  it("ACCENT_COLORS contains expected colors", () => {
    expect(ACCENT_COLORS).toContain("gray");
    expect(ACCENT_COLORS).toContain("gold");
    expect(ACCENT_COLORS).toContain("red");
    expect(ACCENT_COLORS).toContain("blue");
    expect(ACCENT_COLORS).toContain("green");
    expect(ACCENT_COLORS.length).toBe(26);
  });

  it("GRAY_COLORS contains auto and standard gray options", () => {
    expect(GRAY_COLORS).toContain("auto");
    expect(GRAY_COLORS).toContain("gray");
    expect(GRAY_COLORS).toContain("sand");
    expect(GRAY_COLORS).toContain("slate");
    expect(GRAY_COLORS.length).toBe(7);
  });

  it("RADII contains all radius options", () => {
    expect(RADII).toContain("none");
    expect(RADII).toContain("medium");
    expect(RADII).toContain("full");
    expect(RADII.length).toBe(5);
  });

  it("SCALINGS contains percentage values including 100%", () => {
    expect(SCALINGS).toContain("100%");
    expect(SCALINGS).toContain("90%");
    expect(SCALINGS).toContain("110%");
    expect(SCALINGS.length).toBe(5);
  });

  it("PANEL_BACKGROUNDS contains solid and translucent", () => {
    expect(PANEL_BACKGROUNDS).toEqual(["solid", "translucent"]);
  });
});

describe("DEFAULT_THEME_BUILDER_SETTINGS", () => {
  it("has correct default values", () => {
    expect(DEFAULT_THEME_BUILDER_SETTINGS).toEqual({
      accentColor: "gray",
      appearance: "dark",
      codeFont: "System default",
      codeTheme: "GitHub",
      dangerColor: "tomato",
      grayColor: "gray",
      hexOverrides: {
        accentColor: { enabled: false, lightHex: "", darkHex: "" },
        grayColor: { enabled: false, lightHex: "", darkHex: "" },
        dangerColor: { enabled: false, lightHex: "", darkHex: "" },
        successColor: { enabled: false, lightHex: "", darkHex: "" },
        warningColor: { enabled: false, lightHex: "", darkHex: "" },
        infoColor: { enabled: false, lightHex: "", darkHex: "" },
      },
      infoColor: "iris",
      panelBackground: "translucent",
      primaryFont: "System default",
      radius: "medium",
      scaling: "100%",
      successColor: "green",
      warningColor: "amber",
    });
  });

  it("all values are valid options from their respective arrays", () => {
    expect(ACCENT_COLORS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.accentColor);
    expect(GRAY_COLORS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.grayColor);
    expect(RADII).toContain(DEFAULT_THEME_BUILDER_SETTINGS.radius);
    expect(SCALINGS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.scaling);
    expect(PANEL_BACKGROUNDS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.panelBackground);
    expect(ACCENT_COLORS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.dangerColor);
    expect(ACCENT_COLORS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.successColor);
    expect(ACCENT_COLORS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.warningColor);
    expect(ACCENT_COLORS).toContain(DEFAULT_THEME_BUILDER_SETTINGS.infoColor);
  });
});

describe("themeBuilderSettingsAtom", () => {
  it("returns defaults when no value is set", () => {
    const store = createStore();
    const settings = store.get(themeBuilderSettingsAtom);
    expect(settings).toEqual(DEFAULT_THEME_BUILDER_SETTINGS);
  });

  it("can be updated with new settings", () => {
    const store = createStore();
    const newSettings = { ...DEFAULT_THEME_BUILDER_SETTINGS, accentColor: "blue" as const };
    store.set(themeBuilderSettingsAtom, newSettings);
    expect(store.get(themeBuilderSettingsAtom).accentColor).toBe("blue");
  });

  it("preserves other fields on partial update via spread", () => {
    const store = createStore();
    const current = store.get(themeBuilderSettingsAtom);
    store.set(themeBuilderSettingsAtom, { ...current, dangerColor: "crimson" as const });

    const updated = store.get(themeBuilderSettingsAtom);
    expect(updated.dangerColor).toBe("crimson");
    expect(updated.accentColor).toBe("gray");
    expect(updated.radius).toBe("medium");
  });
});

describe("derived atoms", () => {
  it("themeAccentColorAtom returns accentColor from settings", () => {
    const store = createStore();
    expect(store.get(themeAccentColorAtom)).toBe("gray");

    store.set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS, accentColor: "blue" as const });
    expect(store.get(themeAccentColorAtom)).toBe("blue");
  });

  it("themeGrayColorAtom returns grayColor from settings", () => {
    const store = createStore();
    expect(store.get(themeGrayColorAtom)).toBe("gray");

    store.set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS, grayColor: "sand" as const });
    expect(store.get(themeGrayColorAtom)).toBe("sand");
  });

  it("themeAppearanceAtom returns appearance from settings", () => {
    const store = createStore();
    expect(store.get(themeAppearanceAtom)).toBe("dark");

    store.set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS, appearance: "light" as const });
    expect(store.get(themeAppearanceAtom)).toBe("light");
  });

  it("themeDangerColorAtom returns dangerColor from settings", () => {
    const store = createStore();
    expect(store.get(themeDangerColorAtom)).toBe("tomato");

    store.set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS, dangerColor: "red" as const });
    expect(store.get(themeDangerColorAtom)).toBe("red");
  });

  it("themeSuccessColorAtom returns successColor from settings", () => {
    const store = createStore();
    expect(store.get(themeSuccessColorAtom)).toBe("green");

    store.set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS, successColor: "teal" as const });
    expect(store.get(themeSuccessColorAtom)).toBe("teal");
  });

  it("themeWarningColorAtom returns warningColor from settings", () => {
    const store = createStore();
    expect(store.get(themeWarningColorAtom)).toBe("amber");

    store.set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS, warningColor: "orange" as const });
    expect(store.get(themeWarningColorAtom)).toBe("orange");
  });
});
