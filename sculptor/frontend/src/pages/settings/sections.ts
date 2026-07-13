import {
  CodeIcon,
  CogIcon,
  DatabaseIcon,
  FolderTreeIcon,
  GitBranchIcon,
  KeyboardIcon,
  PaintbrushIcon,
  PlayIcon,
  PuzzleIcon,
  ShieldCheckIcon,
  ShieldIcon,
  TerminalIcon,
} from "lucide-react";
import type { ComponentType } from "react";

import { ElementIds } from "../../api";

/**
 * Single source of truth for Settings sections.
 *
 * Both the Settings page sidebar (`SettingsPage.tsx`) and the Cmd+K
 * command palette (`builtinCommands/settings.ts`) consume the
 * `SETTINGS_SECTIONS` array below. Adding, reordering, or renaming a
 * section here propagates to both places automatically — no separate
 * registry to keep in sync.
 *
 * Order in this array IS the rendered order in the sidebar and the
 * palette's "Go to settings..." sub-page.
 */

export const SettingsSection = {
  GENERAL: "GENERAL",
  AGENT: "AGENT",
  KEYBINDINGS: "KEYBINDINGS",
  EXTENSIONS: "EXTENSIONS",
  DEPENDENCIES: "DEPENDENCIES",
  PI: "PI",
  REPOSITORIES: "REPOSITORIES",
  GIT: "GIT",
  CI: "CI",
  FILE_BROWSER: "FILE_BROWSER",
  PROJECT_ENV_VARS: "PROJECT_ENV_VARS",
  PRIVACY: "PRIVACY",
  EXPERIMENTAL: "EXPERIMENTAL",
  ACTIONS: "ACTIONS",
  THEME_BUILDER: "THEME_BUILDER",
} as const;

export type SettingsSectionId = (typeof SettingsSection)[keyof typeof SettingsSection];

type LucideIconType = ComponentType<{ size?: number | string }>;

export type SettingsSectionDescriptor = {
  id: SettingsSectionId;
  /** Sidebar label and palette row title (without the "Settings: " prefix). */
  displayName: string;
  /** Short hint shown in the palette beneath the row title. */
  paletteSubtitle: string;
  /** Extra fuzzy-search keywords for the palette. "settings" / "preferences" are added automatically. */
  paletteKeywords: ReadonlyArray<string>;
  /** Lucide icon used in the palette row. */
  icon: LucideIconType;
  /** Sidebar test id (also used by the palette row when emitted). */
  testId: string;
  /**
   * When set, this section belongs to a visually-grouped run of sections that
   * share this label. A consecutive run of sections with the same `group`
   * renders under a single non-clickable header (the label), is indented, and
   * is closed by a divider after the last member — in both the sidebar and the
   * mobile nav. It is display-only and never becomes a command-palette row.
   */
  group?: string;
};

export const SETTINGS_SECTIONS: ReadonlyArray<SettingsSectionDescriptor> = [
  {
    id: SettingsSection.GENERAL,
    displayName: "General",
    paletteSubtitle: "Theme, updates",
    paletteKeywords: ["theme", "updates"],
    icon: CogIcon,
    testId: ElementIds.SETTINGS_NAV_GENERAL,
  },
  // The Extensions section is always visible: it hosts the extensions master
  // switch, so it must stay reachable even when the system is off (to flip it
  // back on).
  {
    id: SettingsSection.EXTENSIONS,
    displayName: "Extensions",
    paletteSubtitle: "Installed extensions and their settings",
    paletteKeywords: ["plugins", "addons"],
    icon: PuzzleIcon,
    testId: ElementIds.SETTINGS_NAV_EXTENSIONS,
  },
  {
    id: SettingsSection.DEPENDENCIES,
    displayName: "Dependencies",
    paletteSubtitle: "Tools and managers",
    paletteKeywords: ["packages"],
    icon: DatabaseIcon,
    testId: ElementIds.SETTINGS_NAV_DEPENDENCIES,
  },
  {
    id: SettingsSection.AGENT,
    displayName: "Claude",
    group: "Harnesses",
    paletteSubtitle: "Default model and effort",
    paletteKeywords: ["model", "llm", "claude"],
    icon: PlayIcon,
    testId: ElementIds.SETTINGS_NAV_AGENT,
  },
  {
    id: SettingsSection.PI,
    displayName: "Pi",
    group: "Harnesses",
    paletteSubtitle: "Pi harness configuration",
    paletteKeywords: ["pi", "harness", "agent"],
    icon: PlayIcon,
    testId: ElementIds.SETTINGS_NAV_PI,
  },
  {
    id: SettingsSection.KEYBINDINGS,
    displayName: "Keybindings",
    group: "Interface",
    paletteSubtitle: "Customize keyboard shortcuts",
    paletteKeywords: ["shortcuts", "hotkeys"],
    icon: KeyboardIcon,
    testId: ElementIds.SETTINGS_NAV_KEYBINDINGS,
  },
  {
    id: SettingsSection.THEME_BUILDER,
    displayName: "Theme builder",
    group: "Interface",
    paletteSubtitle: "Tweak appearance",
    paletteKeywords: ["colors", "appearance"],
    icon: PaintbrushIcon,
    testId: ElementIds.SETTINGS_NAV_THEME_BUILDER,
  },
  {
    id: SettingsSection.REPOSITORIES,
    displayName: "Repositories",
    group: "Project",
    paletteSubtitle: "Manage repos",
    paletteKeywords: ["repos", "projects"],
    icon: GitBranchIcon,
    testId: ElementIds.SETTINGS_NAV_REPOSITORIES,
  },
  {
    id: SettingsSection.GIT,
    displayName: "Git",
    group: "Project",
    paletteSubtitle: "Git provider configuration",
    paletteKeywords: ["github", "pr", "pull request"],
    icon: GitBranchIcon,
    testId: ElementIds.SETTINGS_NAV_GIT,
  },
  {
    id: SettingsSection.CI,
    displayName: "CI",
    group: "Project",
    paletteSubtitle: "CI Babysitter and CI integrations",
    paletteKeywords: ["pipeline", "babysitter", "ci"],
    icon: ShieldIcon,
    testId: ElementIds.SETTINGS_NAV_CI,
  },
  {
    id: SettingsSection.FILE_BROWSER,
    displayName: "File browser",
    group: "Project",
    paletteSubtitle: "Diff views and tab behavior",
    paletteKeywords: ["diff", "files"],
    icon: FolderTreeIcon,
    testId: ElementIds.SETTINGS_NAV_FILE_BROWSER,
  },
  {
    id: SettingsSection.PROJECT_ENV_VARS,
    displayName: "Environment variables",
    group: "Project",
    paletteSubtitle: "Per-project env",
    paletteKeywords: ["env", "vars"],
    icon: TerminalIcon,
    testId: ElementIds.SETTINGS_NAV_PROJECT_ENV_VARS,
  },
  {
    id: SettingsSection.PRIVACY,
    displayName: "Privacy",
    paletteSubtitle: "Email and telemetry",
    paletteKeywords: ["account", "profile", "telemetry", "tracking", "data", "opt out"],
    icon: ShieldCheckIcon,
    testId: ElementIds.SETTINGS_NAV_PRIVACY,
  },
  {
    id: SettingsSection.EXPERIMENTAL,
    displayName: "Experimental",
    paletteSubtitle: "Feature flags",
    paletteKeywords: ["flags", "beta"],
    icon: ShieldIcon,
    testId: ElementIds.SETTINGS_NAV_EXPERIMENTAL,
  },
  {
    id: SettingsSection.ACTIONS,
    displayName: "Actions",
    paletteSubtitle: "Custom actions",
    paletteKeywords: ["custom"],
    icon: CodeIcon,
    testId: ElementIds.SETTINGS_NAV_ACTIONS,
  },
];
