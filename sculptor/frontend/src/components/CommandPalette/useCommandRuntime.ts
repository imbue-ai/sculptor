import { useSetAtom } from "jotai";
import { useStore } from "jotai/react";
import { useCallback, useLayoutEffect, useMemo, useRef } from "react";

import type { UserConfigField } from "../../api";
import { CHAT_INPUT_ELEMENT_ID } from "../../common/Constants.ts";
import { useImbueNavigate } from "../../common/NavigateUtils.ts";
import { chatSearchFocusRequestAtom, chatSearchVisibleAtom } from "../../common/state/atoms/chatSearch.ts";
import { updateReportProblemAtom } from "../../common/state/atoms/reportProblem.ts";
import { themeBuilderSettingsAtom } from "../../common/state/atoms/themeBuilder.ts";
import { openWorkspaceTabAtom } from "../../common/state/atoms/workspaces.ts";
import { useDevPanel } from "../../common/state/hooks/useDevPanel.ts";
import { useHelpDialog } from "../../common/state/hooks/useHelpDialog.ts";
import { useOpenSettings } from "../../common/state/hooks/useOpenSettings.ts";
import { useUserConfig } from "../../common/state/hooks/useUserConfig.ts";
import type { AppearanceMode } from "../../common/theme/appearanceModes.ts";
import { newWorkspaceModalAtom } from "../newWorkspace/newWorkspaceAtoms.ts";
import { toggleSectionAtom } from "../sections/sectionActions.ts";
import { type CommandActionId, commandActionsAtom } from "./commandActions.ts";
import type { AppStore, CommandRuntime } from "./runtime.ts";

const isElectronAvailable = (): boolean =>
  typeof window !== "undefined" && Boolean((window as { sculptor?: unknown }).sculptor);

const reloadElectronWindow = (): void => {
  // `window.location.reload()` reloads the renderer in both Electron and
  // a plain browser, so no Electron-specific reload path is needed.
  window.location.reload();
};

const focusChatInput = (): void => {
  const chatInput = document.getElementById(CHAT_INPUT_ELEMENT_ID);
  const editable = chatInput?.querySelector<HTMLElement>("[contenteditable='true']");
  editable?.focus();
};

/**
 * Hook variant of `useCallback` whose returned function identity is
 * stable for the lifetime of the calling component, but always invokes
 * the latest closure passed in. Mirrors the userland `useEvent` shim
 * (RFC pending) — used here so each runtime method can be a stable
 * function without React's `useCallback` dep churn cascading into
 * registry re-registrations.
 *
 * The ref assignment runs in a layout effect (not in the render body)
 * so we don't mutate during render — that's the rule the official
 * `useEvent` RFC enforces, and it keeps StrictMode double-renders /
 * concurrent rendering from reading a stale closure.
 */
const useEvent = <TArgs extends ReadonlyArray<unknown>, TResult>(
  fn: (...args: TArgs) => TResult,
): ((...args: TArgs) => TResult) => {
  const ref = useRef(fn);
  useLayoutEffect(() => {
    ref.current = fn;
  });
  return useCallback((...args: TArgs): TResult => ref.current(...args), []);
};

/**
 * Build the `CommandRuntime` object that builtins and dynamic providers
 * close over. Each runtime method is a `useEvent`-style stable callback,
 * so the returned object's identity is stable for the lifetime of the
 * calling component — `staticCommands` and dynamic providers can build
 * once and never re-register on config / navigation / panel-toggle churn.
 */
export const useCommandRuntime = (): CommandRuntime => {
  const store: AppStore = useStore();
  const navigate = useImbueNavigate();
  const openSettings = useOpenSettings();

  const { toggleHelpDialog } = useHelpDialog();
  const { toggleDevPanel } = useDevPanel();
  const toggleSection = useSetAtom(toggleSectionAtom);

  const setThemeSettings = useSetAtom(themeBuilderSettingsAtom);
  const setChatSearchVisible = useSetAtom(chatSearchVisibleAtom);
  const setChatSearchFocus = useSetAtom(chatSearchFocusRequestAtom);
  const updateReportProblem = useSetAtom(updateReportProblemAtom);
  const openWorkspaceTab = useSetAtom(openWorkspaceTabAtom);

  const { updateField } = useUserConfig();

  // Each method below is a useEvent-style stable callback: identity
  // never changes, the body always runs against the latest closure.
  const invokeAction = useEvent((id: CommandActionId): void => {
    const actions = store.get(commandActionsAtom);
    actions[id]?.();
  });

  const toHome = useEvent((): void => navigate.navigateToHome());
  // useOpenSettings adds SETTINGS_TAB to tabOrderAtom in addition to
  // navigating, so the user gets a closeable Settings tab.
  const toSettings = useEvent((section?: string): void => openSettings(section));
  const toAddWorkspace = useEvent((): void => navigate.navigateToAddWorkspace());
  // The palette previously only updated the URL — the tab strip never
  // learned about the navigation, so the user landed on a workspace
  // that wasn't represented as a tab. Open the tab first (idempotent:
  // the atom no-ops if already in the list) so any palette-driven
  // navigation produces the same end state as clicking a tab.
  const toWorkspace = useEvent((workspaceId: string): void => {
    openWorkspaceTab(workspaceId);
    navigate.navigateToWorkspace(workspaceId);
  });
  const toAgent = useEvent((workspaceId: string, agentId: string): void => {
    openWorkspaceTab(workspaceId);
    navigate.navigateToAgent(workspaceId, agentId);
  });
  // Set the modal atom directly (rather than via useSetAtom) so this stays a
  // useEvent-stable callback and the runtime object never churns.
  const openNewWorkspaceModal = useEvent((): void => store.set(newWorkspaceModalAtom, { open: true }));

  const uiToggleHelpDialog = useEvent((): void => toggleHelpDialog());
  const uiToggleDevPanel = useEvent((): void => toggleDevPanel());
  const uiToggleLeftPanel = useEvent((): void => toggleSection({ section: "left" }));
  const uiToggleBottomPanel = useEvent((): void => toggleSection({ section: "bottom" }));
  const uiToggleRightPanel = useEvent((): void => toggleSection({ section: "right" }));
  const setTheme = useEvent((mode: AppearanceMode): void => {
    setThemeSettings((prev) => ({ ...prev, appearance: mode }));
  });
  const uiFocusChatInput = useEvent((): void => focusChatInput());
  const showChatSearch = useEvent((): void => {
    setChatSearchVisible(true);
    setChatSearchFocus((n: number) => n + 1);
  });
  const jumpChatToBottom = useEvent((): void => invokeAction("chat.jumpToBottom"));
  const nextWorkspaceTab = useEvent((): void => invokeAction("workspace.nextTab"));
  const previousWorkspaceTab = useEvent((): void => invokeAction("workspace.previousTab"));
  const nextAgent = useEvent((): void => invokeAction("agent.next"));
  const previousAgent = useEvent((): void => invokeAction("agent.previous"));
  const createAgent = useEvent((): void => invokeAction("agent.create"));
  const openReportProblem = useEvent((): void => updateReportProblem({ isOpen: true }));
  const clearActiveTerminal = useEvent((): void => invokeAction("terminal.clearActive"));

  const updateConfigField = useEvent(
    (field: UserConfigField, value: unknown): Promise<unknown> => updateField(field, value),
  );
  const reloadWindow = useEvent((): void => reloadElectronWindow());

  // The runtime object reference stays stable across renders because
  // every dep below is identity-stable for the lifetime of this
  // component:
  //   - `store` is a Jotai Provider's store (stable per Jotai docs)
  //   - every `useEvent`-stabilized callback has empty `useCallback`
  //     deps, so its identity never changes
  // The dep list is exhaustive (ESLint enforces this) but the memo's
  // recompute path is effectively dead code — it runs once. If a future
  // contributor adds a non-stable value to this list, expect cascading
  // re-registrations of every builtin and dynamic provider.
  // `electron.isAvailable` is a module-level read, not reactive.
  return useMemo<CommandRuntime>(
    () => ({
      // The Jotai Provider's store is referentially stable across
      // renders, so capturing it here is fine — commands that need it
      // call `runtime.store.get(atom)`.
      store,
      navigate: { toHome, toSettings, toAddWorkspace, toWorkspace, toAgent },
      openNewWorkspaceModal,
      ui: {
        toggleHelpDialog: uiToggleHelpDialog,
        toggleDevPanel: uiToggleDevPanel,
        toggleLeftPanel: uiToggleLeftPanel,
        toggleBottomPanel: uiToggleBottomPanel,
        toggleRightPanel: uiToggleRightPanel,
        setTheme,
        focusChatInput: uiFocusChatInput,
        showChatSearch,
        jumpChatToBottom,
        nextWorkspaceTab,
        previousWorkspaceTab,
        nextAgent,
        previousAgent,
        createAgent,
        openReportProblem,
        clearActiveTerminal,
      },
      config: { updateField: updateConfigField },
      electron: { isAvailable: isElectronAvailable(), reloadWindow },
    }),
    [
      store,
      toHome,
      toSettings,
      toAddWorkspace,
      toWorkspace,
      toAgent,
      openNewWorkspaceModal,
      uiToggleHelpDialog,
      uiToggleDevPanel,
      uiToggleLeftPanel,
      uiToggleBottomPanel,
      uiToggleRightPanel,
      setTheme,
      uiFocusChatInput,
      showChatSearch,
      jumpChatToBottom,
      nextWorkspaceTab,
      previousWorkspaceTab,
      nextAgent,
      previousAgent,
      createAgent,
      openReportProblem,
      clearActiveTerminal,
      updateConfigField,
      reloadWindow,
    ],
  );
};
