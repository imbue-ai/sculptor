import type { ReactElement } from "react";
import { useMemo } from "react";

import { buildChatCommands } from "./builtinCommands/chat.ts";
import { buildHelpCommands } from "./builtinCommands/help.ts";
import { buildNavigationCommands } from "./builtinCommands/navigation.ts";
import { buildPanelCommands } from "./builtinCommands/panels.ts";
import { buildSettingsCommands } from "./builtinCommands/settings.ts";
import { buildTerminalCommands } from "./builtinCommands/terminal.ts";
import { buildThemeCommands } from "./builtinCommands/theme.ts";
import { buildWorkspaceActionCommands } from "./builtinCommands/workspaces.ts";
import { WorkspaceDeleteConfirmation } from "./contextActions/WorkspaceDeleteConfirmation.tsx";
import { buildAddPanelProvider } from "./dynamic/addPanel.ts";
import { buildAgentActionsProvider } from "./dynamic/agentActions.ts";
import { buildAgentProvider } from "./dynamic/agentCommands.ts";
import { buildPanelTogglesProvider } from "./dynamic/panels.ts";
import { buildWorkspaceActionsProvider } from "./dynamic/workspaceActions.ts";
import { buildWorkspaceProvider } from "./dynamic/workspaceCommands.tsx";
import { useRegisterCommands, useRegisterDynamicCommands } from "./hooks/useCommandPalette.ts";
import { useCommandRuntime } from "./hooks/useCommandRuntime.ts";
import { useContextActionRuntimes } from "./hooks/useContextActionRuntimes.ts";

/**
 * One-time wiring of all builtin commands and dynamic providers. Mounts as
 * a sibling of the palette (in AppShell). All hooks are extracted:
 *
 *   - `useCommandRuntime`         — builds the stable runtime object.
 *   - `useContextActionRuntimes`  — builds workspace/agent action runtimes.
 *
 * The runtime is stable across the lifetime of this component (each
 * method is a `useEvent`-style stable callback), so `staticCommands`
 * builds once and `registerMany` runs at most once per session — config
 * or keybinding changes do NOT churn the registry.
 *
 * Toggles whose label depends on state flip via
 * `Command.getTitle`/`getSubtitle`/`getIcon` at render time, not by
 * re-registering.
 *
 * Also mounts the headless workspace delete confirmation — the dialog that
 * the palette's Delete action and the delete_workspace keybinding drive via
 * `workspaceDeleteTargetAtom`. It lives here because this is the one mount
 * point shared by every surface that can set the target.
 */
export const CommandRegistrations = (): ReactElement => {
  const runtime = useCommandRuntime();
  const { workspaceActionRuntime, agentActionRuntime } = useContextActionRuntimes();

  const staticCommands = useMemo(
    () => [
      ...buildNavigationCommands(runtime),
      ...buildWorkspaceActionCommands(runtime),
      ...buildSettingsCommands(runtime),
      ...buildPanelCommands(runtime),
      ...buildThemeCommands(runtime),
      ...buildChatCommands(runtime),
      ...buildTerminalCommands(runtime),
      ...buildHelpCommands(runtime),
    ],
    [runtime],
  );
  useRegisterCommands(staticCommands);

  const workspaceProvider = useMemo(() => buildWorkspaceProvider(runtime), [runtime]);
  const agentProvider = useMemo(() => buildAgentProvider(runtime), [runtime]);
  const panelTogglesProvider = useMemo(() => buildPanelTogglesProvider(runtime), [runtime]);
  const addPanelProvider = useMemo(() => buildAddPanelProvider(runtime), [runtime]);
  useRegisterDynamicCommands(workspaceProvider);
  useRegisterDynamicCommands(panelTogglesProvider);
  useRegisterDynamicCommands(agentProvider);
  useRegisterDynamicCommands(addPanelProvider);

  // Context-action providers — drive Cmd+K → Workspace/Agent actions… off
  // the same descriptor lists that the right-click menus consume. Adding
  // a new descriptor in `contextActions/{workspace,agent}Actions.ts`
  // surfaces it in both places.
  const workspaceActionsProvider = useMemo(
    () => buildWorkspaceActionsProvider(runtime, workspaceActionRuntime),
    [runtime, workspaceActionRuntime],
  );
  const agentActionsProvider = useMemo(
    () => buildAgentActionsProvider(runtime, agentActionRuntime),
    [runtime, agentActionRuntime],
  );
  useRegisterDynamicCommands(workspaceActionsProvider);
  useRegisterDynamicCommands(agentActionsProvider);

  return <WorkspaceDeleteConfirmation />;
};
