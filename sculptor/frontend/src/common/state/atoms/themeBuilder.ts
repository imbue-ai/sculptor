import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

import type { AppearanceMode } from "~/common/theme/appearanceModes.ts";
import type { ShikiThemePairName } from "~/common/theme/shikiThemes.ts";
import { DEFAULT_SHIKI_THEME } from "~/common/theme/shikiThemes.ts";

/**
 * Radix UI accent color options.
 * These match the color prop accepted by Radix Theme and Radix components.
 */
export const ACCENT_COLORS = [
  "gray",
  "gold",
  "bronze",
  "brown",
  "yellow",
  "amber",
  "orange",
  "tomato",
  "red",
  "ruby",
  "crimson",
  "pink",
  "plum",
  "purple",
  "violet",
  "iris",
  "indigo",
  "blue",
  "cyan",
  "teal",
  "jade",
  "green",
  "grass",
  "lime",
  "mint",
  "sky",
] as const;

export const GRAY_COLORS = ["auto", "gray", "mauve", "slate", "sage", "olive", "sand"] as const;

export const RADII = ["none", "small", "medium", "large", "full"] as const;

export const SCALINGS = ["90%", "95%", "100%", "105%", "110%"] as const;

export const PANEL_BACKGROUNDS = ["solid", "translucent"] as const;

export const FONT_OPTIONS = [
  "System default",
  "Inter",
  "JetBrains Mono",
  "ABC Diatype Variable Unlicensed Trial",
  "ABC Diatype Mono Variable Unlicensed Trial",
  "ABC Diatype Semi-Mono Variable Unlicensed Trial",
] as const;

export type AccentColor = (typeof ACCENT_COLORS)[number];
export type GrayColor = (typeof GRAY_COLORS)[number];
export type Radius = (typeof RADII)[number];
export type Scaling = (typeof SCALINGS)[number];
export type PanelBackground = (typeof PANEL_BACKGROUNDS)[number];
export type FontOption = (typeof FONT_OPTIONS)[number];

export type HexOverride = {
  enabled: boolean;
  lightHex: string;
  darkHex: string;
};

export const COLOR_SETTING_KEYS = [
  "accentColor",
  "grayColor",
  "dangerColor",
  "successColor",
  "warningColor",
  "infoColor",
] as const;

export type ColorSettingKey = (typeof COLOR_SETTING_KEYS)[number];

export type HexOverrides = Record<ColorSettingKey, HexOverride>;

export type ThemeBuilderSettings = {
  accentColor: AccentColor;
  appearance: AppearanceMode;
  codeFont: FontOption;
  codeTheme: ShikiThemePairName;
  dangerColor: AccentColor;
  grayColor: GrayColor;
  hexOverrides: HexOverrides;
  infoColor: AccentColor;
  panelBackground: PanelBackground;
  primaryFont: FontOption;
  radius: Radius;
  scaling: Scaling;
  successColor: AccentColor;
  warningColor: AccentColor;
};

const DEFAULT_HEX_OVERRIDE: HexOverride = {
  enabled: false,
  lightHex: "",
  darkHex: "",
};

export const DEFAULT_HEX_OVERRIDES: HexOverrides = {
  accentColor: { ...DEFAULT_HEX_OVERRIDE },
  grayColor: { ...DEFAULT_HEX_OVERRIDE },
  dangerColor: { ...DEFAULT_HEX_OVERRIDE },
  successColor: { ...DEFAULT_HEX_OVERRIDE },
  warningColor: { ...DEFAULT_HEX_OVERRIDE },
  infoColor: { ...DEFAULT_HEX_OVERRIDE },
};

export const DEFAULT_THEME_BUILDER_SETTINGS: ThemeBuilderSettings = {
  accentColor: "gray",
  appearance: "dark",
  codeFont: "System default",
  codeTheme: DEFAULT_SHIKI_THEME,
  dangerColor: "tomato",
  grayColor: "gray",
  hexOverrides: { ...DEFAULT_HEX_OVERRIDES },
  infoColor: "iris",
  panelBackground: "translucent",
  primaryFont: "System default",
  radius: "medium",
  scaling: "100%",
  successColor: "green",
  warningColor: "amber",
};

/**
 * PRIMARY ATOM: Theme Builder Settings
 *
 * Persisted to localStorage via atomWithStorage so preferences survive
 * across sessions without requiring backend API changes.
 */
export const themeBuilderSettingsAtom = atomWithStorage<ThemeBuilderSettings>(
  "sculptor-theme-builder",
  DEFAULT_THEME_BUILDER_SETTINGS,
);

// Derived atoms for individual settings

export const themeAccentColorAtom = atom<AccentColor>((get) => get(themeBuilderSettingsAtom).accentColor);

export const themeGrayColorAtom = atom<GrayColor>((get) => get(themeBuilderSettingsAtom).grayColor);

export const themeAppearanceAtom = atom<AppearanceMode>((get) => get(themeBuilderSettingsAtom).appearance);

export const themeDangerColorAtom = atom<AccentColor>((get) => get(themeBuilderSettingsAtom).dangerColor);

export const themeSuccessColorAtom = atom<AccentColor>((get) => get(themeBuilderSettingsAtom).successColor);

export const themeWarningColorAtom = atom<AccentColor>((get) => get(themeBuilderSettingsAtom).warningColor);

export const themeCodeThemeAtom = atom<ShikiThemePairName>(
  (get) => get(themeBuilderSettingsAtom).codeTheme ?? DEFAULT_SHIKI_THEME,
);
