import { MoonIcon, PaletteIcon } from "lucide-react";

import { themeBuilderSettingsAtom } from "~/common/state/atoms/themeBuilder.ts";
import { APPEARANCE_MODES } from "~/common/theme/appearanceModes.ts";

import type { Command } from "../types/commandPalette.ts";
import type { CommandRuntime } from "../utils/runtime.ts";

// Theme commands make up the "view" group (see groups.ts — heading is
// "Theme"); panel / section rows live in the separate "panels" group.
export const buildThemeCommands = (runtime: CommandRuntime): Array<Command> => [
  {
    id: "theme.toggle",
    title: "Toggle theme",
    subtitle: "Quickly flip between light and dark",
    keywords: ["dark", "light"],
    group: "view",
    icon: MoonIcon,
    shortcut: "toggle_theme",
    // Promoted to primary so it shares the primary tier with the other
    // root-level Theme entries.
    primary: true,
    // Order 10 so this leads `theme.switch` (order 20) in the static
    // sort. Both score the same on the "theme" query (word-prefix tier
    // × primary boost), so cmdk's stable sort breaks the tie via DOM
    // order — which `groupCommands` sets from `order`. Toggle is the
    // more direct action, so it should be the first hit.
    order: 10,
    perform: (): void => {
      // Read the user's preference via the atom store. We toggle BETWEEN
      // explicit light/dark — if the user is on "system" we flip to the
      // opposite of whatever the OS resolves to right now. Falls back to
      // dark when uncertain.
      const current = runtime.store.get(themeBuilderSettingsAtom).appearance;
      const isDarkResolved =
        current === "dark" ||
        (current === "system" &&
          typeof window !== "undefined" &&
          window.matchMedia?.("(prefers-color-scheme: dark)").matches);
      runtime.ui.setTheme(isDarkResolved ? "light" : "dark");
    },
    keepOpen: true,
  },
  {
    id: "theme.switch",
    title: "Switch theme...",
    subtitle: "Light, dark, or system",
    keywords: ["appearance", "color", "mode"],
    group: "view",
    icon: PaletteIcon,
    pageId: "theme.appearance",
    primary: true,
    order: 20,
    perform: (): void => {
      // Page push handled by runner.
    },
  },
  // Sub-page rows for picking a specific appearance mode. Driven by
  // APPEARANCE_MODES so adding a new mode (e.g. "Auto") in
  // ~/common/theme/appearanceModes.ts surfaces here automatically — and
  // appearanceModesDrift.test.ts asserts the two stay in sync.
  ...APPEARANCE_MODES.map(
    (mode): Command => ({
      id: `theme.appearance.${mode.id}`,
      title: mode.label,
      subtitle: mode.paletteSubtitle,
      keywords: [...mode.paletteKeywords],
      group: "view",
      icon: mode.icon,
      onPage: "theme.appearance",
      perform: () => runtime.ui.setTheme(mode.id),
    }),
  ),
];
