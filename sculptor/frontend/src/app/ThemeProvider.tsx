import { Theme as RadixTheme } from "@radix-ui/themes";
import type { CSSProperties, PropsWithChildren, ReactElement } from "react";
import { useLayoutEffect, useMemo, useRef } from "react";

import type { ColorSettingKey, HexOverrides, ThemeBuilderSettings } from "~/common/state/atoms/themeBuilder.ts";
import { COLOR_SETTING_KEYS, DEFAULT_HEX_OVERRIDES } from "~/common/state/atoms/themeBuilder.ts";
import { useResolvedTheme } from "~/common/state/hooks/useResolvedTheme.ts";
import { useThemeBuilderSettings } from "~/common/state/hooks/useThemeBuilder.ts";
import { generateColorScale, isValidHex } from "~/common/theme/generateColorScale.ts";
import { getColorScale, resolveGrayColor } from "~/common/theme/radixColorHexMap.ts";

/**
 * Maps a ColorSettingKey to the CSS variable prefix used by Radix.
 * accentColor -> "accent", grayColor -> "gray", dangerColor/successColor/etc. -> their color name.
 */
/** Number of steps in a Radix color scale (--<color>-1 through --<color>-12). */
const COLOR_SCALE_STEPS = 12;

const getCssVarPrefix = (key: ColorSettingKey, settings: ThemeBuilderSettings): string => {
  switch (key) {
    case "accentColor":
      return settings.accentColor;
    case "grayColor": {
      const resolved = resolveGrayColor(settings.grayColor, settings.accentColor);
      return resolved;
    }
    case "dangerColor":
      return settings.dangerColor;
    case "successColor":
      return settings.successColor;
    case "warningColor":
      return settings.warningColor;
    case "infoColor":
      return settings.infoColor;
  }
};

const buildHexOverrideStyles = (
  hexOverrides: HexOverrides,
  resolvedAppearance: "light" | "dark",
  settings: ThemeBuilderSettings,
): CSSProperties => {
  const cssVars: Record<string, string> = {};

  for (const key of COLOR_SETTING_KEYS) {
    const override = hexOverrides[key];
    if (!override.enabled) {
      continue;
    }

    const hex = resolvedAppearance === "light" ? override.lightHex : override.darkHex;
    if (hex === "" || !isValidHex(hex)) {
      continue;
    }

    const prefix = getCssVarPrefix(key, settings);
    const scale = generateColorScale(hex, resolvedAppearance);
    const defaultScale = getColorScale(prefix, resolvedAppearance);

    for (let step = 1; step <= COLOR_SCALE_STEPS; step++) {
      const customValue = scale[step - 1];
      const defaultValue = defaultScale[step - 1];
      // Only override if the custom scale differs from the default
      if (customValue !== defaultValue) {
        cssVars[`--${prefix}-${step}`] = customValue;
      }
    }

    // For accentColor, also override the --accent-N aliases that Radix uses
    if (key === "accentColor") {
      for (let step = 1; step <= COLOR_SCALE_STEPS; step++) {
        cssVars[`--accent-${step}`] = scale[step - 1];
      }
    }

    // For grayColor, also override the --gray-N aliases
    if (key === "grayColor") {
      for (let step = 1; step <= COLOR_SCALE_STEPS; step++) {
        cssVars[`--gray-${step}`] = scale[step - 1];
      }
    }
  }

  return cssVars as CSSProperties;
};

/** System-default fallback stacks matching index.css. */
const SYSTEM_DEFAULT_FONT = '"Inter", sans-serif';
const SYSTEM_MONO_FONT = '"JetBrains Mono", monospace';

const buildFontStyles = (primaryFont: string | undefined, codeFont: string | undefined): CSSProperties | undefined => {
  const isCustomPrimary = primaryFont !== undefined && primaryFont !== "System default";
  const isCustomCode = codeFont !== undefined && codeFont !== "System default";

  if (!isCustomPrimary && !isCustomCode) {
    return undefined;
  }

  const vars: Record<string, string> = {};

  if (isCustomPrimary) {
    const fontStack = `"${primaryFont}", ${SYSTEM_DEFAULT_FONT}`;
    vars["--default-font-family"] = fontStack;
    vars["--heading-font-family"] = fontStack;
    vars["--strong-font-family"] = fontStack;
    vars["--em-font-family"] = fontStack;
    vars["--quote-font-family"] = fontStack;
  }

  if (isCustomCode) {
    const monoStack = `"${codeFont}", ${SYSTEM_MONO_FONT}`;
    vars["--code-font-family"] = monoStack;
    vars["--mono-font-family"] = monoStack;
    // Pierre diffs: CSS custom properties inherit through shadow DOM
    vars["--diffs-font-family"] = monoStack;
  }

  return vars as CSSProperties;
};

export const ImbueTheme = ({ children }: PropsWithChildren): ReactElement => {
  const appearance = useResolvedTheme();
  const settings = useThemeBuilderSettings();
  const hexOverrides = settings.hexOverrides ?? DEFAULT_HEX_OVERRIDES;

  const hasAnyHexOverride = COLOR_SETTING_KEYS.some((key) => hexOverrides[key].enabled);

  const overrideStyles = useMemo(() => {
    if (!hasAnyHexOverride) {
      return undefined;
    }
    return buildHexOverrideStyles(hexOverrides, appearance, settings);
  }, [hasAnyHexOverride, hexOverrides, appearance, settings]);

  const fontStyles = useMemo(
    () => buildFontStyles(settings.primaryFont, settings.codeFont),
    [settings.primaryFont, settings.codeFont],
  );

  // Track whether this is the initial mount (no theme switch yet).
  const prevAppearanceRef = useRef(appearance);

  // Mirror the appearance class onto <html>. The Radix token scales are keyed
  // on .dark/.light, and index.css paints <html>'s background from them — the
  // backdrop the browser exposes during window resizes and paint lag. Without
  // this the tokens only exist inside the app root and <html> stays white.
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.remove(appearance === "light" ? "dark" : "light");
    root.classList.add(appearance);
  }, [appearance]);

  // Work around two issues that cause a visible flash on theme toggle:
  //
  // 1. Radix Theme's internal useEffect-based appearance sync — it copies
  //    the `appearance` prop into local state via useEffect, so the CSS
  //    class ("light"/"dark") updates one frame late. We eagerly apply the
  //    correct class here before the browser paints.
  //
  // 2. CSS transitions on background-color / color (used by tabs, buttons,
  //    etc.) cause old theme colors to *animate* to new values instead of
  //    snapping instantly. We suppress all transitions for one frame during
  //    the switch, then re-enable them.
  useLayoutEffect(() => {
    const isThemeSwitch = prevAppearanceRef.current !== appearance;
    prevAppearanceRef.current = appearance;
    if (!isThemeSwitch) return;

    // Fix the Radix Theme root class immediately.
    const el = document.querySelector<HTMLElement>('.radix-themes[data-is-root-theme="true"]');
    if (el) {
      const stale = appearance === "light" ? "dark" : "light";
      if (el.classList.contains(stale)) {
        el.classList.remove(stale);
        el.classList.add(appearance);
      }
    }

    // Suppress CSS transitions so colors snap to the new theme instantly.
    document.documentElement.classList.add("theme-switching");
    requestAnimationFrame(() => {
      document.documentElement.classList.remove("theme-switching");
    });
  }, [appearance]);

  return (
    <RadixTheme
      accentColor={settings.accentColor}
      appearance={appearance}
      grayColor={settings.grayColor}
      panelBackground={settings.panelBackground}
      radius={settings.radius}
      scaling={settings.scaling}
      style={fontStyles}
    >
      <div style={overrideStyles}>{children}</div>
    </RadixTheme>
  );
};

export const ThemeProvider = ({ children }: PropsWithChildren): ReactElement => {
  return <ImbueTheme>{children}</ImbueTheme>;
};
