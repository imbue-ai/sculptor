import type { BundledTheme } from "shiki/bundle/web";

/**
 * Shiki syntax highlighting theme pairs.
 *
 * Each entry maps a user-facing label to a { light, dark } pair of bundled
 * shiki theme IDs. These are used by the alpha chat code blocks and the
 * Pierre diff panel so syntax highlighting stays consistent across the app.
 *
 * Both theme IDs in a pair must be valid `BundledTheme` members of
 * `shiki/bundle/web`; the `satisfies` check below enforces that at compile
 * time, so an unbundled ID fails the build rather than failing at runtime.
 */
export const SHIKI_THEME_PAIRS = {
  GitHub: { light: "github-light", dark: "github-dark" },
  "GitHub Dimmed": { light: "github-light", dark: "github-dark-dimmed" },
  Catppuccin: { light: "catppuccin-latte", dark: "catppuccin-mocha" },
  Dracula: { light: "github-light", dark: "dracula" },
  Everforest: { light: "everforest-light", dark: "everforest-dark" },
  Gruvbox: { light: "gruvbox-light-medium", dark: "gruvbox-dark-medium" },
  Material: { light: "material-theme-lighter", dark: "material-theme" },
  Min: { light: "min-light", dark: "min-dark" },
  "Night Owl": { light: "night-owl-light", dark: "night-owl" },
  Nord: { light: "nord", dark: "nord" },
  One: { light: "one-light", dark: "one-dark-pro" },
  "Rosé Pine": { light: "rose-pine-dawn", dark: "rose-pine" },
  Solarized: { light: "solarized-light", dark: "solarized-dark" },
  "Tokyo Night": { light: "tokyo-night", dark: "tokyo-night" },
  Vitesse: { light: "vitesse-light", dark: "vitesse-dark" },
} as const satisfies Record<string, { light: BundledTheme; dark: BundledTheme }>;

export type ShikiThemePairName = keyof typeof SHIKI_THEME_PAIRS;

export const SHIKI_THEME_PAIR_NAMES = Object.keys(SHIKI_THEME_PAIRS) as ReadonlyArray<ShikiThemePairName>;

export const DEFAULT_SHIKI_THEME: ShikiThemePairName = "GitHub";

/** Resolve the current theme pair from a pair name. */
export const getShikiThemes = (name: ShikiThemePairName): { light: BundledTheme; dark: BundledTheme } => {
  return SHIKI_THEME_PAIRS[name];
};
