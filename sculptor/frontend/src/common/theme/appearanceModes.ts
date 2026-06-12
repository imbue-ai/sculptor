import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";

/**
 * Single source of truth for the three appearance modes the app
 * supports. Both the Settings appearance picker and the Cmd+K palette
 * iterate this list, so adding a new mode propagates to both surfaces
 * without needing to remember a second hard-coded list.
 *
 * `paletteSubtitle` and `paletteKeywords` are palette-specific metadata;
 * the Settings UI ignores them. Keeping them here (rather than in a
 * sibling file) means a new mode can't be added without thinking about
 * how it should appear in fuzzy search.
 */
export const APPEARANCE_MODES = [
  {
    id: "light",
    label: "Light",
    paletteSubtitle: "Light appearance",
    paletteKeywords: ["bright"],
    icon: SunIcon,
  },
  {
    id: "dark",
    label: "Dark",
    paletteSubtitle: "Dark appearance",
    paletteKeywords: ["night"],
    icon: MoonIcon,
  },
  {
    id: "system",
    label: "System",
    paletteSubtitle: "Match operating system",
    paletteKeywords: ["auto"],
    icon: MonitorIcon,
  },
] as const;

export type AppearanceMode = (typeof APPEARANCE_MODES)[number]["id"];
