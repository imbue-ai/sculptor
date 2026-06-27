import { PaletteIcon } from "lucide-react";

import { SETTINGS_SECTIONS } from "~/pages/settings/sections.ts";

import type { CommandRuntime } from "../runtime.ts";
import type { Command } from "../types.ts";

/**
 * Strong demote applied to every page-scoped Settings sub-page row.
 * Settings sections share names with action commands (e.g. "File browser"
 * vs. "Toggle File browser") and an exact title match would otherwise
 * dominate fuzzy searches that the user almost certainly intended for the
 * action. The demote is sized so a settings sub-page row falls below
 * *any* matching non-settings row:
 *
 *   max settings.page.* score after demote
 *     = SCORE_EXACT × PAGE_SCOPED_PENALTY × DEMOTE
 *     = 1000 × 0.25 × 0.0001 = 0.025
 *
 *   min plausible non-settings score (page-scoped subsequence floor)
 *     = SCORE_SUBSEQ_FLOOR × PAGE_SCOPED_PENALTY = 1.0 × 0.25 = 0.25
 *
 * 0.025 < 0.25, so any other matching row wins. When *only* settings
 * sub-pages match, they still appear (score stays positive).
 */
const SETTINGS_PAGE_DEMOTE = 0.0001;

/**
 * Build the Settings commands surfaced in Cmd+K. The list of sections
 * is single-sourced from `~/pages/settings/sections.ts` — same module
 * the Settings page sidebar consumes — so adding/renaming a section in
 * one place propagates here. Each section becomes one page-scoped
 * palette row under the `settings.section` sub-page; fuzzy search at
 * the root surfaces them under top-level commands via the page-scope
 * penalty.
 */
export const buildSettingsCommands = (runtime: CommandRuntime): Array<Command> => {
  const commands: Array<Command> = [
    {
      id: "settings.open",
      title: "Go to settings...",
      subtitle: "All settings sections",
      keywords: ["preferences", "config", "open"],
      group: "navigation",
      icon: PaletteIcon,
      pageId: "settings.section",
      // Intentionally not `primary`: the Navigation group reads
      // top-down as Go to workspace... (primary) → Open home →
      // Open settings → Go to settings... — driven by explicit `order`
      // values. Promoting this to primary would lift it above the
      // direct-nav entries, which the Open/Go-to convention puts above
      // the picker.
      order: 30,
      perform: (): void => {
        // The pageId push is handled by the runner; nothing else to do.
      },
    },
  ];

  for (const entry of SETTINGS_SECTIONS) {
    // Page-scoped variant under the "settings.section" sub-page. Section
    // names are kept off the root palette to avoid flooding it; they
    // surface either by opening the sub-page, or via fuzzy search at the
    // root (which reveals sub-page contents below top-level matches).
    commands.push({
      id: `settings.page.${entry.id.toLowerCase()}`,
      title: entry.displayName,
      subtitle: entry.paletteSubtitle,
      keywords: ["settings", "preferences", ...entry.paletteKeywords],
      group: "navigation",
      icon: entry.icon,
      onPage: "settings.section",
      boost: SETTINGS_PAGE_DEMOTE,
      perform: () => runtime.navigate.toSettings(entry.id),
    });
  }

  return commands;
};
