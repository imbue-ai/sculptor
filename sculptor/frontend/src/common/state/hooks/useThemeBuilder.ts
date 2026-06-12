import { useAtomValue } from "jotai";

import type { AccentColor, GrayColor, ThemeBuilderSettings } from "../atoms/themeBuilder";
import {
  themeAccentColorAtom,
  themeAppearanceAtom,
  themeBuilderSettingsAtom,
  themeDangerColorAtom,
  themeGrayColorAtom,
  themeSuccessColorAtom,
  themeWarningColorAtom,
} from "../atoms/themeBuilder";

export const useThemeDangerColor = (): AccentColor => {
  return useAtomValue(themeDangerColorAtom);
};

export const useThemeSuccessColor = (): AccentColor => {
  return useAtomValue(themeSuccessColorAtom);
};

export const useThemeWarningColor = (): AccentColor => {
  return useAtomValue(themeWarningColorAtom);
};

export const useThemeAccentColor = (): AccentColor => {
  return useAtomValue(themeAccentColorAtom);
};

export const useThemeGrayColor = (): GrayColor => {
  return useAtomValue(themeGrayColorAtom);
};

export const useThemeAppearance = (): "light" | "dark" | "system" => {
  return useAtomValue(themeAppearanceAtom);
};

export const useThemeBuilderSettings = (): ThemeBuilderSettings => {
  return useAtomValue(themeBuilderSettingsAtom);
};
