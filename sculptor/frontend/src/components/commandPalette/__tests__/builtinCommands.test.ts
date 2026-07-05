import { getDefaultStore } from "jotai";
import { Maximize2, Minimize2 } from "lucide-react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_THEME_BUILDER_SETTINGS, themeBuilderSettingsAtom } from "../../../common/state/atoms/themeBuilder.ts";
import { chatToolDensityAtom } from "../../../pages/workspace/chatAlpha/atoms.ts";
import { buildChatCommands } from "../builtinCommands/chat.ts";
import { buildHelpCommands } from "../builtinCommands/help.ts";
import { buildNavigationCommands } from "../builtinCommands/navigation.ts";
import { buildPanelCommands } from "../builtinCommands/panels.ts";
import { buildSettingsCommands } from "../builtinCommands/settings.ts";
import { buildTerminalCommands } from "../builtinCommands/terminal.ts";
import { buildThemeCommands } from "../builtinCommands/theme.ts";
import { buildWorkspaceActionCommands } from "../builtinCommands/workspaces.ts";
import type { Command, PaletteContext } from "../types/commandPalette.ts";
import type { CommandRuntime } from "../utils/runtime.ts";

const ROOT_CTX: PaletteContext = {
  route: { isHome: true, isWorkspace: false, isSettings: false, isAgent: false },
  activeWorkspaceId: null,
  activeAgentId: null,
  hasChatPanel: false,
  hasTerminalPanel: false,
  isSectionMaximized: false,
  page: null,
};

const WORKSPACE_CTX: PaletteContext = {
  ...ROOT_CTX,
  route: { isHome: false, isWorkspace: true, isSettings: false, isAgent: false },
};

const SETTINGS_CTX: PaletteContext = {
  ...ROOT_CTX,
  route: { isHome: false, isWorkspace: false, isSettings: true, isAgent: false },
};

// A context where no top-level route is active (every route flag false). Used
// to assert that route-gated commands stay hidden when nothing is selected.
const NO_ACTIVE_ROUTE_CTX: PaletteContext = {
  ...ROOT_CTX,
  route: { isHome: false, isWorkspace: false, isSettings: false, isAgent: false },
};

const WORKSPACE_WITH_CHAT_CTX: PaletteContext = {
  ...WORKSPACE_CTX,
  hasChatPanel: true,
};

const WORKSPACE_WITH_TERMINAL_CTX: PaletteContext = {
  ...WORKSPACE_CTX,
  hasTerminalPanel: true,
};

const makeRuntime = (overrides: Partial<CommandRuntime> = {}): CommandRuntime => {
  const noop = (): void => {};
  const base: CommandRuntime = {
    store: getDefaultStore(),
    navigate: {
      toHome: vi.fn(),
      toSettings: vi.fn(),
      toWorkspace: vi.fn(),
      toAgent: vi.fn(),
    },
    openNewWorkspaceDialog: vi.fn(),
    ui: {
      toggleHelpDialog: vi.fn(),
      toggleDevPanel: vi.fn(),
      toggleLeftPanel: vi.fn(),
      toggleBottomPanel: vi.fn(),
      toggleRightPanel: vi.fn(),
      toggleSidebar: vi.fn(),
      toggleMaximizeSection: vi.fn(),
      setTheme: vi.fn(),
      focusChatInput: vi.fn(),
      showChatSearch: vi.fn(),
      jumpChatToBottom: vi.fn(),
      nextWorkspaceTab: vi.fn(),
      previousWorkspaceTab: vi.fn(),
      nextAgent: vi.fn(),
      previousAgent: vi.fn(),
      createAgent: vi.fn(),
      openReportProblem: vi.fn(),
      clearActiveTerminal: vi.fn(),
    },
    config: { updateField: vi.fn().mockResolvedValue(undefined) },
    electron: { isAvailable: false, reloadWindow: noop },
  };
  return { ...base, ...overrides } as CommandRuntime;
};

const runPerform = (cmd: Command, ctx: PaletteContext = ROOT_CTX): void => {
  cmd.perform({ ctx, keepOpen: false, pushPage: vi.fn() });
};

beforeEach(() => {
  // Reset the theme atom to a known state so tests don't bleed into each other.
  getDefaultStore().set(themeBuilderSettingsAtom, { ...DEFAULT_THEME_BUILDER_SETTINGS });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildNavigationCommands", () => {
  it("emits exactly the expected command ids", () => {
    const cmds = buildNavigationCommands(makeRuntime());
    expect(cmds.map((c) => c.id).sort()).toEqual(
      ["nav.home", "nav.settings", "nav.new_workspace", "nav.new_agent"].sort(),
    );
  });

  it("nav.home perform calls runtime.navigate.toHome", () => {
    const runtime = makeRuntime();
    const cmd = buildNavigationCommands(runtime).find((c) => c.id === "nav.home")!;
    runPerform(cmd);
    expect(runtime.navigate.toHome).toHaveBeenCalledTimes(1);
  });

  it("nav.settings perform calls runtime.navigate.toSettings with no args", () => {
    const runtime = makeRuntime();
    const cmd = buildNavigationCommands(runtime).find((c) => c.id === "nav.settings")!;
    runPerform(cmd);
    expect(runtime.navigate.toSettings).toHaveBeenCalledTimes(1);
    expect(runtime.navigate.toSettings).toHaveBeenCalledWith();
  });

  it("nav.new_workspace perform opens the new-workspace dialog", () => {
    const runtime = makeRuntime();
    const cmd = buildNavigationCommands(runtime).find((c) => c.id === "nav.new_workspace")!;
    runPerform(cmd);
    expect(runtime.openNewWorkspaceDialog).toHaveBeenCalledTimes(1);
  });

  it("nav.settings is titled 'Open settings' (direct nav, distinct from settings.open's 'Go to settings...' picker)", () => {
    const cmd = buildNavigationCommands(makeRuntime()).find((c) => c.id === "nav.settings")!;
    expect(cmd.title).toBe("Open settings");
  });

  it("nav.new_workspace lives in the Workspaces group (not Navigation) and is primary so it leads", () => {
    const cmd = buildNavigationCommands(makeRuntime()).find((c) => c.id === "nav.new_workspace")!;
    expect(cmd.group).toBe("workspaces");
    expect(cmd.primary).toBe(true);
  });

  it("nav.new_agent perform calls runtime.ui.createAgent", () => {
    const runtime = makeRuntime();
    const cmd = buildNavigationCommands(runtime).find((c) => c.id === "nav.new_agent")!;
    runPerform(cmd);
    expect(runtime.ui.createAgent).toHaveBeenCalledTimes(1);
  });

  it("nav.new_agent is gated on a concrete active workspace, not just the route flags", () => {
    // createAgent needs a workspace to add the agent to. The `agent.create`
    // action it dispatches is registered by useWorkspaceShellBootstrap, which
    // only mounts under an active workspace, so gating this row on the id
    // (not route.isWorkspace) keeps the two in sync — and keeps it visible on
    // agent sub-routes, mirroring the dynamic agent provider.
    const cmd = buildNavigationCommands(makeRuntime()).find((c) => c.id === "nav.new_agent")!;
    const inWorkspace: PaletteContext = { ...WORKSPACE_CTX, activeWorkspaceId: "ws-1" };
    expect(cmd.when!(inWorkspace)).toBe(true);
    expect(cmd.when!(WORKSPACE_CTX)).toBe(false);
    expect(cmd.when!(ROOT_CTX)).toBe(false);
    expect(cmd.when!(SETTINGS_CTX)).toBe(false);
    expect(cmd.when!(NO_ACTIVE_ROUTE_CTX)).toBe(false);
  });

  it("nav.new_agent lives in the Workspaces group and declares the new_agent shortcut", () => {
    const cmd = buildNavigationCommands(makeRuntime()).find((c) => c.id === "nav.new_agent")!;
    expect(cmd.group).toBe("workspaces");
    expect(cmd.shortcut).toBe("new_agent");
  });
});

describe("buildWorkspaceActionCommands", () => {
  it("emits exactly the expected command ids", () => {
    // Closing the current workspace is now handled by the dynamic
    // "Close" entry on the workspace.actions sub-page (see
    // dynamic/workspaceActions.ts), so it is intentionally absent here.
    const cmds = buildWorkspaceActionCommands(makeRuntime());
    expect(cmds.map((c) => c.id).sort()).toEqual(
      ["workspaces.next_tab", "workspaces.previous_tab", "agents.next", "agents.previous"].sort(),
    );
  });

  it("does NOT emit workspaces.close_current (consolidated into the workspace.actions Close entry)", () => {
    const cmds = buildWorkspaceActionCommands(makeRuntime());
    expect(cmds.find((c) => c.id === "workspaces.close_current")).toBeUndefined();
  });

  it("tab navigation lives on workspace.actions; agent navigation on agents.switch", () => {
    const cmds = buildWorkspaceActionCommands(makeRuntime());
    const expectedPage: Record<string, string> = {
      "workspaces.next_tab": "workspace.actions",
      "workspaces.previous_tab": "workspace.actions",
      "agents.next": "agents.switch",
      "agents.previous": "agents.switch",
    };
    for (const cmd of cmds) {
      expect(cmd.onPage).toBe(expectedPage[cmd.id]);
    }
  });

  it("workspace.actions sub-page surfaces every command (no when predicate hides them there)", () => {
    // The sub-page is only entered when `ctx.activeWorkspaceId` is set
    // (the entry-point guards that), so we don't re-gate at the row level.
    const cmds = buildWorkspaceActionCommands(makeRuntime());
    for (const cmd of cmds) {
      expect(cmd.when).toBeUndefined();
    }
  });

  it("each command's shortcut field matches its keybinding id", () => {
    const cmds = buildWorkspaceActionCommands(makeRuntime());
    const expected: Record<string, string> = {
      "workspaces.next_tab": "next_tab",
      "workspaces.previous_tab": "previous_tab",
      "agents.next": "next_agent",
      "agents.previous": "previous_agent",
    };
    for (const cmd of cmds) {
      expect(cmd.shortcut).toBe(expected[cmd.id]);
    }
  });

  it("perform delegates to the matching runtime.ui method", () => {
    const runtime = makeRuntime();
    const cmds = buildWorkspaceActionCommands(runtime);
    runPerform(cmds.find((c) => c.id === "workspaces.next_tab")!);
    runPerform(cmds.find((c) => c.id === "workspaces.previous_tab")!);
    runPerform(cmds.find((c) => c.id === "agents.next")!);
    runPerform(cmds.find((c) => c.id === "agents.previous")!);
    expect(runtime.ui.nextWorkspaceTab).toHaveBeenCalledTimes(1);
    expect(runtime.ui.previousWorkspaceTab).toHaveBeenCalledTimes(1);
    expect(runtime.ui.nextAgent).toHaveBeenCalledTimes(1);
    expect(runtime.ui.previousAgent).toHaveBeenCalledTimes(1);
  });
});

describe("buildSettingsCommands", () => {
  it("emits exactly one root command: settings.open with pageId and no onPage", () => {
    const cmds = buildSettingsCommands(makeRuntime());
    const rootCmds = cmds.filter((c) => c.onPage === undefined);
    expect(rootCmds).toHaveLength(1);
    const open = rootCmds[0]!;
    expect(open.id).toBe("settings.open");
    expect(open.pageId).toBe("settings.section");
    expect(open.onPage).toBeUndefined();
  });

  it("all non-root commands are page-scoped to settings.section", () => {
    const cmds = buildSettingsCommands(makeRuntime());
    for (const cmd of cmds) {
      if (cmd.id === "settings.open") continue;
      expect(cmd.onPage).toBe("settings.section");
    }
  });

  it("does not emit any leftover root-level settings.<section> commands", () => {
    const cmds = buildSettingsCommands(makeRuntime());
    const rootSettingsRegex = /^settings\.[a-z_]+$/;
    for (const cmd of cmds) {
      if (cmd.id === "settings.open") continue;
      // All other commands must be either page-scoped (no root id matching
      // the regex) or have an id under the settings.page.* namespace.
      if (rootSettingsRegex.test(cmd.id)) {
        // If the id matches the simple regex it must still be page-scoped.
        expect(cmd.onPage).toBe("settings.section");
      }
    }
    // Explicitly: no root-only command other than settings.open has the
    // simple settings.<section> shape.
    const offenders = cmds.filter(
      (c) => c.id !== "settings.open" && c.onPage === undefined && rootSettingsRegex.test(c.id),
    );
    expect(offenders).toEqual([]);
  });

  it("page-scoped command titles do not begin with 'Settings: '", () => {
    const cmds = buildSettingsCommands(makeRuntime());
    for (const cmd of cmds) {
      if (cmd.id === "settings.open") continue;
      expect(cmd.title.startsWith("Settings: ")).toBe(false);
    }
  });

  it("performing settings.page.general calls runtime.navigate.toSettings('GENERAL')", () => {
    const runtime = makeRuntime();
    const cmd = buildSettingsCommands(runtime).find((c) => c.id === "settings.page.general")!;
    expect(cmd).toBeDefined();
    runPerform(cmd);
    expect(runtime.navigate.toSettings).toHaveBeenCalledWith("GENERAL");
  });

  it("every settings sub-page row carries a demote boost so it ranks below other matches", () => {
    // Settings sub-page rows share names with action commands (e.g. "File
    // browser" vs. "Toggle File browser"). The demote boost is what makes
    // the action win when the user fuzzy-searches the shared name.
    const cmds = buildSettingsCommands(makeRuntime());
    for (const cmd of cmds) {
      if (cmd.id === "settings.open") continue;
      expect(cmd.boost).toBeDefined();
      expect(cmd.boost!).toBeGreaterThan(0);
      expect(cmd.boost!).toBeLessThan(1);
    }
  });
});

describe("buildPanelCommands", () => {
  it("emits exactly the expected command ids", () => {
    const cmds = buildPanelCommands(makeRuntime());
    expect(cmds.map((c) => c.id).sort()).toEqual(
      [
        "view.toggle_layout",
        "view.toggle_panels",
        "view.toggle_left_panel",
        "view.toggle_right_panel",
        "view.toggle_bottom_panel",
        "view.toggle_sidebar",
        "view.maximize_section",
      ].sort(),
    );
  });

  it("the two root entry-points push the layout / panels sub-pages", () => {
    const cmds = buildPanelCommands(makeRuntime());
    const layoutOpener = cmds.find((c) => c.id === "view.toggle_layout")!;
    const panelsOpener = cmds.find((c) => c.id === "view.toggle_panels")!;
    expect(layoutOpener.pageId).toBe("view.layout");
    expect(layoutOpener.onPage).toBeUndefined();
    expect(layoutOpener.primary).toBe(true);
    expect(panelsOpener.pageId).toBe("view.panels");
    expect(panelsOpener.onPage).toBeUndefined();
    expect(panelsOpener.primary).toBe(true);
  });

  it("the panels page-opener uses show/focus language, not toggle", () => {
    const cmds = buildPanelCommands(makeRuntime());
    const panelsOpener = cmds.find((c) => c.id === "view.toggle_panels")!;
    expect(panelsOpener.title).toBe("Show panel...");
  });

  it('does NOT use the word "plugin" in any user-visible string', () => {
    // Coworker feedback: "plugin" is jargon coworkers don't recognise.
    const cmds = buildPanelCommands(makeRuntime());
    for (const cmd of cmds) {
      expect(cmd.title.toLowerCase()).not.toContain("plugin");
      expect((cmd.subtitle ?? "").toLowerCase()).not.toContain("plugin");
      for (const k of cmd.keywords ?? []) {
        expect(k.toLowerCase()).not.toContain("plugin");
      }
    }
  });

  it("section toggles are scoped to the view.layout sub-page", () => {
    const cmds = buildPanelCommands(makeRuntime());
    for (const id of ["view.toggle_left_panel", "view.toggle_right_panel", "view.toggle_bottom_panel"]) {
      const cmd = cmds.find((c) => c.id === id)!;
      expect(cmd.onPage).toBe("view.layout");
    }
  });

  it("when predicates require route.isWorkspace, except the sidebar toggle", () => {
    // The sidebar rail is app-shell chrome mounted on every route (workspace,
    // Home, Settings), so its toggle is deliberately ungated. The section/layout
    // commands act on workspace sections and stay workspace-only.
    const cmds = buildPanelCommands(makeRuntime());
    for (const cmd of cmds) {
      if (cmd.id === "view.toggle_sidebar") {
        expect(cmd.when).toBeUndefined();
        continue;
      }
      expect(cmd.when).toBeDefined();
      expect(cmd.when!(WORKSPACE_CTX)).toBe(true);
      expect(cmd.when!(ROOT_CTX)).toBe(false);
      expect(cmd.when!(SETTINGS_CTX)).toBe(false);
      expect(cmd.when!(NO_ACTIVE_ROUTE_CTX)).toBe(false);
    }
  });

  it("the three section-toggle commands have keepOpen: true", () => {
    const cmds = buildPanelCommands(makeRuntime());
    const byId = (id: string): Command => cmds.find((c) => c.id === id)!;
    expect(byId("view.toggle_left_panel").keepOpen).toBe(true);
    expect(byId("view.toggle_right_panel").keepOpen).toBe(true);
    expect(byId("view.toggle_bottom_panel").keepOpen).toBe(true);
  });

  it("perform delegates to the matching runtime.ui method", () => {
    const runtime = makeRuntime();
    const cmds = buildPanelCommands(runtime);
    runPerform(cmds.find((c) => c.id === "view.toggle_left_panel")!);
    runPerform(cmds.find((c) => c.id === "view.toggle_right_panel")!);
    runPerform(cmds.find((c) => c.id === "view.toggle_bottom_panel")!);
    runPerform(cmds.find((c) => c.id === "view.toggle_sidebar")!);
    runPerform(cmds.find((c) => c.id === "view.maximize_section")!);
    expect(runtime.ui.toggleLeftPanel).toHaveBeenCalledTimes(1);
    expect(runtime.ui.toggleRightPanel).toHaveBeenCalledTimes(1);
    expect(runtime.ui.toggleBottomPanel).toHaveBeenCalledTimes(1);
    expect(runtime.ui.toggleSidebar).toHaveBeenCalledTimes(1);
    expect(runtime.ui.toggleMaximizeSection).toHaveBeenCalledTimes(1);
  });

  it("the sidebar toggle keeps the palette open; the maximize toggle closes it", () => {
    const cmds = buildPanelCommands(makeRuntime());
    expect(cmds.find((c) => c.id === "view.toggle_sidebar")!.keepOpen).toBe(true);
    expect(cmds.find((c) => c.id === "view.maximize_section")!.keepOpen).not.toBe(true);
  });

  it("view.maximize_section lives on the view.layout sub-page", () => {
    const cmd = buildPanelCommands(makeRuntime()).find((c) => c.id === "view.maximize_section")!;
    expect(cmd.onPage).toBe("view.layout");
  });

  it("view.maximize_section flips title/subtitle/icon on isSectionMaximized", () => {
    // The command toggles, so its copy names the action it will perform: it
    // reads "Maximize" while nothing is maximized and "Minimize" once a
    // section is maximized.
    const cmd = buildPanelCommands(makeRuntime()).find((c) => c.id === "view.maximize_section")!;
    const notMaximized: PaletteContext = { ...WORKSPACE_CTX, isSectionMaximized: false };
    const maximized: PaletteContext = { ...WORKSPACE_CTX, isSectionMaximized: true };

    expect(cmd.getTitle!(notMaximized)).toBe("Maximize section");
    expect(cmd.getTitle!(maximized)).toBe("Minimize section");

    expect(cmd.getSubtitle!(notMaximized)).toBe("Maximize the active section");
    expect(cmd.getSubtitle!(maximized)).toBe("Restore the maximized section to the normal layout");

    expect(cmd.getIcon!(notMaximized)).toBe(Maximize2);
    expect(cmd.getIcon!(maximized)).toBe(Minimize2);
  });
});

describe("buildThemeCommands", () => {
  it("emits exactly the expected command ids", () => {
    const cmds = buildThemeCommands(makeRuntime());
    expect(cmds.map((c) => c.id).sort()).toEqual(
      [
        "theme.switch",
        "theme.toggle",
        "theme.appearance.light",
        "theme.appearance.dark",
        "theme.appearance.system",
      ].sort(),
    );
  });

  it("theme.switch is a page-opener with pageId 'theme.appearance' and no onPage", () => {
    const cmd = buildThemeCommands(makeRuntime()).find((c) => c.id === "theme.switch")!;
    expect(cmd.pageId).toBe("theme.appearance");
    expect(cmd.onPage).toBeUndefined();
  });

  it("theme.toggle is a root command with keepOpen: true", () => {
    const cmd = buildThemeCommands(makeRuntime()).find((c) => c.id === "theme.toggle")!;
    expect(cmd.onPage).toBeUndefined();
    expect(cmd.pageId).toBeUndefined();
    expect(cmd.keepOpen).toBe(true);
  });

  it("the three appearance commands are scoped to theme.appearance", () => {
    const cmds = buildThemeCommands(makeRuntime());
    for (const id of ["theme.appearance.light", "theme.appearance.dark", "theme.appearance.system"]) {
      const cmd = cmds.find((c) => c.id === id)!;
      expect(cmd.onPage).toBe("theme.appearance");
    }
  });

  it("theme.toggle flips light -> dark when the current appearance is light", () => {
    getDefaultStore().set(themeBuilderSettingsAtom, (prev) => ({ ...prev, appearance: "light" }));
    const runtime = makeRuntime();
    const cmd = buildThemeCommands(runtime).find((c) => c.id === "theme.toggle")!;
    runPerform(cmd);
    expect(runtime.ui.setTheme).toHaveBeenCalledWith("dark");
  });

  it("theme.toggle flips dark -> light when the current appearance is dark", () => {
    getDefaultStore().set(themeBuilderSettingsAtom, (prev) => ({ ...prev, appearance: "dark" }));
    const runtime = makeRuntime();
    const cmd = buildThemeCommands(runtime).find((c) => c.id === "theme.toggle")!;
    runPerform(cmd);
    expect(runtime.ui.setTheme).toHaveBeenCalledWith("light");
  });

  it("each appearance command calls runtime.ui.setTheme with its mode", () => {
    const runtime = makeRuntime();
    const cmds = buildThemeCommands(runtime);
    runPerform(cmds.find((c) => c.id === "theme.appearance.light")!);
    expect(runtime.ui.setTheme).toHaveBeenLastCalledWith("light");
    runPerform(cmds.find((c) => c.id === "theme.appearance.dark")!);
    expect(runtime.ui.setTheme).toHaveBeenLastCalledWith("dark");
    runPerform(cmds.find((c) => c.id === "theme.appearance.system")!);
    expect(runtime.ui.setTheme).toHaveBeenLastCalledWith("system");
  });
});

describe("buildChatCommands", () => {
  it("emits exactly the expected command ids", () => {
    const cmds = buildChatCommands(makeRuntime());
    expect(cmds.map((c) => c.id).sort()).toEqual(
      ["chat.focus_input", "chat.search", "chat.jump_bottom", "chat.toggle_tool_density"].sort(),
    );
  });

  it("chat.focus_input.when requires hasChatPanel (not surfaced on AddWorkspace)", () => {
    // Title says "Focus chat input" — must not surface anywhere a chat
    // input doesn't exist. The `focus_input` keybinding handler in
    // useGlobalKeyboardShortcuts handles AddWorkspace's name input
    // separately (and as a keyboard-only fallback).
    const cmd = buildChatCommands(makeRuntime()).find((c) => c.id === "chat.focus_input")!;
    expect(cmd.when!(ROOT_CTX)).toBe(false);
    expect(cmd.when!(WORKSPACE_CTX)).toBe(false);
    expect(cmd.when!(WORKSPACE_WITH_CHAT_CTX)).toBe(true);
    expect(cmd.when!(NO_ACTIVE_ROUTE_CTX)).toBe(false);
  });

  it("chat.search and chat.jump_bottom both require hasChatPanel", () => {
    const cmds = buildChatCommands(makeRuntime());
    for (const id of ["chat.search", "chat.jump_bottom"]) {
      const cmd = cmds.find((c) => c.id === id)!;
      expect(cmd.when).toBeDefined();
      expect(cmd.when!(WORKSPACE_WITH_CHAT_CTX)).toBe(true);
      expect(cmd.when!(WORKSPACE_CTX)).toBe(false);
      expect(cmd.when!(NO_ACTIVE_ROUTE_CTX)).toBe(false);
      expect(cmd.when!(ROOT_CTX)).toBe(false);
    }
  });

  it("perform delegates to the matching runtime.ui method", () => {
    const runtime = makeRuntime();
    const cmds = buildChatCommands(runtime);
    runPerform(cmds.find((c) => c.id === "chat.focus_input")!);
    runPerform(cmds.find((c) => c.id === "chat.search")!);
    runPerform(cmds.find((c) => c.id === "chat.jump_bottom")!);
    expect(runtime.ui.focusChatInput).toHaveBeenCalledTimes(1);
    expect(runtime.ui.showChatSearch).toHaveBeenCalledTimes(1);
    expect(runtime.ui.jumpChatToBottom).toHaveBeenCalledTimes(1);
  });

  describe("chat.toggle_tool_density", () => {
    afterEach(() => {
      // Reset to default so a flipped value doesn't leak into other tests.
      getDefaultStore().set(chatToolDensityAtom, "default");
    });

    it("requires hasChatPanel", () => {
      const cmd = buildChatCommands(makeRuntime()).find((c) => c.id === "chat.toggle_tool_density")!;
      expect(cmd.when!(WORKSPACE_WITH_CHAT_CTX)).toBe(true);
      expect(cmd.when!(WORKSPACE_CTX)).toBe(false);
      expect(cmd.when!(ROOT_CTX)).toBe(false);
    });

    it("declares the matching keybinding shortcut id", () => {
      const cmd = buildChatCommands(makeRuntime()).find((c) => c.id === "chat.toggle_tool_density")!;
      expect(cmd.shortcut).toBe("toggle_tool_density");
    });

    it("closes the palette after running (the user sees the new density immediately)", () => {
      const cmd = buildChatCommands(makeRuntime()).find((c) => c.id === "chat.toggle_tool_density")!;
      expect(cmd.keepOpen).not.toBe(true);
    });

    it("perform flips default -> expanded -> default", () => {
      const runtime = makeRuntime();
      const cmd = buildChatCommands(runtime).find((c) => c.id === "chat.toggle_tool_density")!;

      runtime.store.set(chatToolDensityAtom, "default");
      runPerform(cmd);
      expect(runtime.store.get(chatToolDensityAtom)).toBe("expanded");

      runPerform(cmd);
      expect(runtime.store.get(chatToolDensityAtom)).toBe("default");
    });

    it("getTitle reflects the current density", () => {
      const runtime = makeRuntime();
      const cmd = buildChatCommands(runtime).find((c) => c.id === "chat.toggle_tool_density")!;

      runtime.store.set(chatToolDensityAtom, "default");
      expect(cmd.getTitle!(WORKSPACE_WITH_CHAT_CTX)).toBe("Expand tool calls");

      runtime.store.set(chatToolDensityAtom, "expanded");
      expect(cmd.getTitle!(WORKSPACE_WITH_CHAT_CTX)).toBe("Compact tool calls");
    });
  });
});

describe("buildTerminalCommands", () => {
  it("emits exactly the expected command ids", () => {
    const cmds = buildTerminalCommands(makeRuntime());
    expect(cmds.map((c) => c.id).sort()).toEqual(["terminal.clear"].sort());
  });

  it("terminal.clear is in the terminal group", () => {
    const cmd = buildTerminalCommands(makeRuntime()).find((c) => c.id === "terminal.clear")!;
    expect(cmd.group).toBe("terminal");
  });

  it("terminal.clear declares the matching keybinding shortcut id", () => {
    const cmd = buildTerminalCommands(makeRuntime()).find((c) => c.id === "terminal.clear")!;
    expect(cmd.shortcut).toBe("clear_terminal");
  });

  it("terminal.clear.when requires hasTerminalPanel (not surfaced where no terminal exists)", () => {
    // The palette path clears the active terminal regardless of focus, so
    // surfacing the row anywhere without a terminal mounted would be a
    // no-op that confuses the user. Gate is parallel to chat.* + hasChatPanel.
    const cmd = buildTerminalCommands(makeRuntime()).find((c) => c.id === "terminal.clear")!;
    expect(cmd.when).toBeDefined();
    expect(cmd.when!(WORKSPACE_WITH_TERMINAL_CTX)).toBe(true);
    expect(cmd.when!(WORKSPACE_CTX)).toBe(false);
    expect(cmd.when!(ROOT_CTX)).toBe(false);
    expect(cmd.when!(SETTINGS_CTX)).toBe(false);
    expect(cmd.when!(NO_ACTIVE_ROUTE_CTX)).toBe(false);
  });

  it("perform delegates to runtime.ui.clearActiveTerminal", () => {
    const runtime = makeRuntime();
    const cmd = buildTerminalCommands(runtime).find((c) => c.id === "terminal.clear")!;
    runPerform(cmd);
    expect(runtime.ui.clearActiveTerminal).toHaveBeenCalledTimes(1);
  });
});

describe("buildHelpCommands", () => {
  it("emits exactly the expected command ids", () => {
    const cmds = buildHelpCommands(makeRuntime());
    expect(cmds.map((c) => c.id).sort()).toEqual(["help.shortcuts", "help.report_problem"].sort());
  });

  it("help.report_problem is in the help group with no onPage and no pageId", () => {
    const cmd = buildHelpCommands(makeRuntime()).find((c) => c.id === "help.report_problem")!;
    expect(cmd.group).toBe("help");
    expect(cmd.onPage).toBeUndefined();
    expect(cmd.pageId).toBeUndefined();
  });

  it("performing help.report_problem calls runtime.ui.openReportProblem exactly once", () => {
    const runtime = makeRuntime();
    const cmd = buildHelpCommands(runtime).find((c) => c.id === "help.report_problem")!;
    runPerform(cmd);
    expect(runtime.ui.openReportProblem).toHaveBeenCalledTimes(1);
  });

  it("help.shortcuts calls runtime.ui.toggleHelpDialog", () => {
    const runtime = makeRuntime();
    const cmd = buildHelpCommands(runtime).find((c) => c.id === "help.shortcuts")!;
    runPerform(cmd);
    expect(runtime.ui.toggleHelpDialog).toHaveBeenCalledTimes(1);
  });

  it("does NOT emit help.dialog (consolidated into help.shortcuts since the dialog is the shortcuts reference)", () => {
    const cmds = buildHelpCommands(makeRuntime());
    expect(cmds.find((c) => c.id === "help.dialog")).toBeUndefined();
  });
});

describe("invariants", () => {
  it("no builtin command claims the `command_palette` keybinding as its own shortcut", () => {
    // The Cmd+K-while-open close path lives in `useGlobalKeyboardShortcuts`
    // (see the special-case block before the overlay-suppression rule).
    // The in-palette window listener at `CommandPalette.tsx` walks the
    // visible commands and intercepts any keystroke that matches one of
    // their `shortcut` ids — so if a command ever claimed `command_palette`,
    // Cmd+K would fire that command instead of closing the palette, and
    // the whole "press the open key again to close" gesture would silently
    // break. Keep this guard so a future contributor can't regress it.
    const runtime = makeRuntime();
    const allBuiltinCmds: Array<Command> = [
      ...buildNavigationCommands(runtime),
      ...buildWorkspaceActionCommands(runtime),
      ...buildSettingsCommands(runtime),
      ...buildPanelCommands(runtime),
      ...buildThemeCommands(runtime),
      ...buildChatCommands(runtime),
      ...buildTerminalCommands(runtime),
      ...buildHelpCommands(runtime),
    ];
    const offenders = allBuiltinCmds.filter((c) => c.shortcut === "command_palette");
    expect(offenders).toEqual([]);
  });
});
