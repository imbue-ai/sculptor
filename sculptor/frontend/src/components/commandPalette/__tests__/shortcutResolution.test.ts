import { getDefaultStore } from "jotai";
import { describe, expect, it, vi } from "vitest";

import { KEYBINDING_DEFINITIONS } from "~/common/keybindings/definitions.ts";
import type { KeybindingId } from "~/common/keybindings/types.ts";

import { buildChatCommands } from "../builtinCommands/chat.ts";
import { buildHelpCommands } from "../builtinCommands/help.ts";
import { buildNavigationCommands } from "../builtinCommands/navigation.ts";
import { buildPanelCommands } from "../builtinCommands/panels.ts";
import { buildSettingsCommands } from "../builtinCommands/settings.ts";
import { buildTerminalCommands } from "../builtinCommands/terminal.ts";
import { buildThemeCommands } from "../builtinCommands/theme.ts";
import { buildWorkspaceActionCommands } from "../builtinCommands/workspaces.ts";
import { buildAgentActions } from "../contextActions/agentActions.ts";
import type { AgentActionRuntime, WorkspaceActionRuntime } from "../contextActions/types.ts";
import { buildWorkspaceActions } from "../contextActions/workspaceActions.ts";
import { buildWorkspaceProvider } from "../dynamic/workspaceCommands.tsx";
import type { Command, PaletteContext } from "../types/commandPalette.ts";
import type { CommandRuntime } from "../utils/runtime.ts";

/**
 * Drift guardrail for keybinding ids referenced from palette commands.
 *
 * `Command.shortcut` and `WorkspaceAction.paletteShortcut` are typed as
 * `KeybindingId` — a union maintained by hand in `~/common/keybindings/
 * types.ts`. The runtime data lives in `KEYBINDING_DEFINITIONS` in a
 * separate file. A typo or rename can leave the type system happy while
 * `keybindingsMap[id]` returns `undefined` at runtime, silently dropping
 * the kbd hint from the palette row. This test enumerates every
 * shortcut a palette row could carry and asserts each id is backed by a
 * real definition.
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
      setTheme: noop,
      focusChatInput: noop,
      showChatSearch: noop,
      jumpChatToBottom: noop,
      nextWorkspaceTab: noop,
      previousWorkspaceTab: noop,
      nextAgent: noop,
      previousAgent: noop,
      openReportProblem: noop,
      clearActiveTerminal: noop,
    },
    config: { updateField: vi.fn().mockResolvedValue(undefined) },
    electron: { isAvailable: false, reloadWindow: noop },
  }) as unknown as CommandRuntime;

const WORKSPACE_CTX: PaletteContext = {
  route: { isHome: false, isWorkspace: true, isSettings: false, isAgent: false },
  activeWorkspaceId: "ws-1",
  activeAgentId: null,
  hasChatPanel: true,
  hasTerminalPanel: false,
  isSectionMaximized: false,
  page: null,
};

const collectStaticShortcuts = (): Array<KeybindingId> => {
  const runtime = makeRuntime();
  const cmds: Array<Command> = [
    ...buildNavigationCommands(runtime),
    ...buildWorkspaceActionCommands(runtime),
    ...buildSettingsCommands(runtime),
    ...buildPanelCommands(runtime),
    ...buildThemeCommands(runtime),
    ...buildChatCommands(runtime),
    ...buildTerminalCommands(runtime),
    ...buildHelpCommands(runtime),
  ];
  return cmds.flatMap((c) => (c.shortcut != null ? [c.shortcut] : []));
};

const collectDynamicShortcuts = (): Array<KeybindingId> => {
  const runtime = makeRuntime();
  const provider = buildWorkspaceProvider(runtime);
  return provider.produce(WORKSPACE_CTX).flatMap((c) => (c.shortcut != null ? [c.shortcut] : []));
};

const collectDescriptorShortcuts = (): Array<KeybindingId> => {
  // Both descriptor lists feed dynamic providers that copy
  // `paletteShortcut` straight onto the Command's `shortcut`. We don't
  // need to invoke the providers — checking the descriptor source
  // covers every shortcut they could ever surface. The builders only
  // assemble static descriptors here; the runtime methods live inside
  // closures the descriptors never call, so an empty stub is enough.
  const wsRuntime = {} as unknown as WorkspaceActionRuntime;
  const agRuntime = {} as unknown as AgentActionRuntime;
  const out: Array<KeybindingId> = [];
  for (const a of buildWorkspaceActions(wsRuntime)) {
    if (a.paletteShortcut != null) out.push(a.paletteShortcut);
  }

  for (const a of buildAgentActions(agRuntime)) {
    if (a.paletteShortcut != null) out.push(a.paletteShortcut);
  }
  return out;
};

describe("Palette shortcut resolution", () => {
  it("every shortcut id referenced by a palette command resolves to a real KEYBINDING_DEFINITIONS entry", () => {
    // Coverage caveat: this walks the seven static builders, the
    // workspace switcher dynamic provider, and the workspace/agent
    // action descriptors — every place a `shortcut: ...` literal lives
    // today. A new builder added to CommandRegistrations.tsx without
    // being added to `collectStaticShortcuts` above would escape the
    // check. The CommandRegistrations file is short enough that a code
    // reviewer should catch the omission; if the surface grows, a more
    // robust registry-walking test would be worth the complexity.
    const definedIds = new Set(KEYBINDING_DEFINITIONS.map((d) => d.id));
    const allShortcuts = [...collectStaticShortcuts(), ...collectDynamicShortcuts(), ...collectDescriptorShortcuts()];
    expect(allShortcuts.length).toBeGreaterThan(0);
    const unresolved = allShortcuts.filter((id) => !definedIds.has(id));
    expect(unresolved).toEqual([]);
  });
});
