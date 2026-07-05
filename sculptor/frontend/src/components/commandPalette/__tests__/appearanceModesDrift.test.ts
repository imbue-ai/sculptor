import { getDefaultStore } from "jotai";
import { describe, expect, it, vi } from "vitest";

import { APPEARANCE_MODES } from "~/common/theme/appearanceModes.ts";

import { buildThemeCommands } from "../builtinCommands/theme.ts";
import type { CommandRuntime } from "../utils/runtime.ts";

/**
 * Drift guardrail mirroring `settingsSectionDrift.test.ts`. The
 * Settings appearance picker (`ThemeBuilderSection.tsx`) and the Cmd+K
 * palette both iterate `APPEARANCE_MODES`. If a future change adds /
 * renames / drops a mode in only one consumer, this test fails.
 *
 * Why a test rather than just relying on the shared array: the type
 * system catches removed modes (because `setTheme` is typed
 * `AppearanceMode`), but it does NOT catch a rename or a missing
 * palette row when a new mode is added — both consumers iterate the
 * array, so they're in sync by construction, but a developer who
 * forgets to import APPEARANCE_MODES and hard-codes a new picker
 * elsewhere wouldn't be caught by typing alone.
 */

const noop = (): void => {};

const makeRuntime = (): CommandRuntime =>
  ({
    store: getDefaultStore(),
    navigate: { toHome: noop, toSettings: vi.fn(), toWorkspace: vi.fn(), toAgent: vi.fn() },
    openNewWorkspaceDialog: noop,
    ui: {
      toggleHelpDialog: noop,
      toggleDevPanel: noop,
      toggleLeftPanel: noop,
      toggleBottomPanel: noop,
      toggleRightPanel: noop,
      setTheme: vi.fn(),
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

describe("Appearance modes drift", () => {
  it("every mode in APPEARANCE_MODES has a corresponding palette command", () => {
    const cmds = buildThemeCommands(makeRuntime());
    const cmdIds = new Set(cmds.map((c) => c.id));
    for (const mode of APPEARANCE_MODES) {
      expect(cmdIds.has(`theme.appearance.${mode.id}`)).toBe(true);
    }
  });

  it("every theme.appearance.* command corresponds to a real mode in APPEARANCE_MODES", () => {
    const cmds = buildThemeCommands(makeRuntime()).filter((c) => c.id.startsWith("theme.appearance."));
    const modeIds = new Set(APPEARANCE_MODES.map((m) => `theme.appearance.${m.id}`));
    for (const cmd of cmds) {
      expect(modeIds.has(cmd.id)).toBe(true);
    }
  });

  it("palette command title matches the picker label (no rename drift)", () => {
    const cmds = buildThemeCommands(makeRuntime());
    for (const mode of APPEARANCE_MODES) {
      const cmd = cmds.find((c) => c.id === `theme.appearance.${mode.id}`);
      expect(cmd?.title).toBe(mode.label);
    }
  });

  it("palette command performs runtime.ui.setTheme with the mode id", () => {
    const runtime = makeRuntime();
    for (const mode of APPEARANCE_MODES) {
      const cmd = buildThemeCommands(runtime).find((c) => c.id === `theme.appearance.${mode.id}`);
      expect(cmd).toBeDefined();
      cmd!.perform({
        ctx: {
          route: { isHome: true, isWorkspace: false, isSettings: false, isAgent: false },
          activeWorkspaceId: null,
          activeAgentId: null,
          hasChatPanel: false,
          hasTerminalPanel: false,
          isSectionMaximized: false,
          page: null,
        },
        keepOpen: false,
        pushPage: vi.fn(),
      });
      expect(runtime.ui.setTheme).toHaveBeenLastCalledWith(mode.id);
    }
  });
});
