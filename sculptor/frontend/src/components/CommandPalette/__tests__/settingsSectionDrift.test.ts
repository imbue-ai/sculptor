import { getDefaultStore } from "jotai";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { UserConfig } from "~/api";
import { SETTINGS_SECTIONS, SettingsSection } from "~/pages/settings/sections.ts";

import { DEFAULT_THEME_BUILDER_SETTINGS, themeBuilderSettingsAtom } from "../../../common/state/atoms/themeBuilder.ts";
import { userConfigAtom } from "../../../common/state/atoms/userConfig.ts";
import { buildSettingsCommands } from "../builtinCommands/settings.ts";
import type { CommandRuntime } from "../runtime.ts";

/**
 * Drift guardrail: the Settings page sidebar AND the Cmd+K palette read
 * from the same `SETTINGS_SECTIONS` array. If a future change drops or
 * renames a section in only one of those consumers, this test fails.
 */

const noop = (): void => {};

const makeRuntime = (): CommandRuntime =>
  ({
    store: getDefaultStore(),
    navigate: { toHome: noop, toSettings: vi.fn(), toAddWorkspace: noop, toWorkspace: vi.fn(), toAgent: vi.fn() },
    openNewWorkspaceModal: noop,
    ui: {
      toggleHelpDialog: noop,
      toggleDevPanel: noop,
      toggleLeftPanel: noop,
      toggleBottomPanel: noop,
      toggleRightPanel: noop,
      setTheme: noop,
      focusChatInput: noop,
      showChatSearch: noop,
      jumpChatToBottom: noop,
      nextWorkspaceTab: noop,
      previousWorkspaceTab: noop,
      nextAgent: noop,
      previousAgent: noop,
      openReportProblem: noop,
    },
    config: { updateField: vi.fn().mockResolvedValue(undefined) },
    electron: { isAvailable: false, reloadWindow: noop },
  }) as unknown as CommandRuntime;

describe("Settings section drift", () => {
  // The Plugins section is gated on the experimental frontend-plugins flag
  // at both consumers; turn it on so the parity checks cover every section.
  beforeEach(() => {
    getDefaultStore().set(userConfigAtom, { enableFrontendPlugins: true } as unknown as UserConfig);
  });

  it("every section in SETTINGS_SECTIONS has a corresponding palette command", () => {
    getDefaultStore().set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS });
    const cmds = buildSettingsCommands(makeRuntime());
    const cmdIds = new Set(cmds.map((c) => c.id));
    for (const section of SETTINGS_SECTIONS) {
      const expectedId = `settings.page.${section.id.toLowerCase()}`;
      expect(cmdIds.has(expectedId)).toBe(true);
    }
  });

  it("every page-scoped settings command corresponds to a real section in SETTINGS_SECTIONS", () => {
    const cmds = buildSettingsCommands(makeRuntime()).filter((c) => c.id.startsWith("settings.page."));
    const sectionIds = new Set(SETTINGS_SECTIONS.map((s) => `settings.page.${s.id.toLowerCase()}`));
    for (const cmd of cmds) {
      expect(sectionIds.has(cmd.id)).toBe(true);
    }
  });

  it("palette command title matches the sidebar display name (no rename drift)", () => {
    const cmds = buildSettingsCommands(makeRuntime());
    for (const section of SETTINGS_SECTIONS) {
      const cmd = cmds.find((c) => c.id === `settings.page.${section.id.toLowerCase()}`);
      expect(cmd?.title).toBe(section.displayName);
    }
  });

  it("excludes the Plugins section when the frontend-plugins flag is off", () => {
    getDefaultStore().set(userConfigAtom, null);
    const cmds = buildSettingsCommands(makeRuntime());
    expect(cmds.some((c) => c.id === `settings.page.${SettingsSection.PLUGINS.toLowerCase()}`)).toBe(false);
  });

  it("palette command performs runtime.navigate.toSettings with the section id", () => {
    const runtime = makeRuntime();
    for (const section of SETTINGS_SECTIONS) {
      const cmd = buildSettingsCommands(runtime).find((c) => c.id === `settings.page.${section.id.toLowerCase()}`);
      expect(cmd).toBeDefined();
      cmd!.perform({
        ctx: {
          route: { isHome: true, isWorkspace: false, isSettings: false, isAddWorkspace: false, isAgent: false },
          activeWorkspaceId: null,
          activeAgentId: null,
          hasChatPanel: false,
          hasTerminalPanel: false,
          page: null,
        },
        keepOpen: false,
        pushPage: vi.fn(),
      });
      expect(runtime.navigate.toSettings).toHaveBeenLastCalledWith(section.id);
    }
  });
});
