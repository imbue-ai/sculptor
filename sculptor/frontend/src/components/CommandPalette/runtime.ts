import type { useStore } from "jotai/react";

import type { UserConfigField } from "~/api";
import type { AppearanceMode } from "~/common/theme/appearanceModes.ts";

/**
 * The Jotai store used by the React tree. We pass it through the runtime
 * so dynamic providers (which run outside React) read from the *Provider's*
 * store rather than the module-level `getDefaultStore()` — those are two
 * different stores when the app wraps in a `<JotaiProvider>`.
 */
export type AppStore = ReturnType<typeof useStore>;

/**
 * Runtime services that the static builtin commands need access to.
 *
 * Builtins are pure functions that return Command[]; they receive a Runtime
 * object built once from React hooks at the top of the tree (see
 * `useCommandRuntime`). This keeps the registry data-only while still
 * letting commands hit useImbueNavigate, useUserConfig, panel toggles, etc.
 */
export type CommandRuntime = {
  /** Jotai store (the one the React tree subscribes to). */
  store: AppStore;
  navigate: {
    toHome: () => void;
    toSettings: (section?: string) => void;
    toAddWorkspace: () => void;
    toWorkspace: (workspaceId: string) => void;
    toAgent: (workspaceId: string, agentId: string) => void;
  };
  /**
   * Open the global new-workspace dialog. Distinct from `navigate.toAddWorkspace`
   * (the legacy `/ws/new` page): the dialog is mounted globally and is the
   * sanctioned create surface, so palette/keyboard entry points open it rather
   * than navigating away.
   */
  openNewWorkspaceModal: () => void;
  ui: {
    toggleHelpDialog: () => void;
    toggleDevPanel: () => void;
    toggleZenMode: () => void;
    toggleFocusMode: () => void;
    toggleLeftPanel: () => void;
    toggleBottomPanel: () => void;
    toggleRightPanel: () => void;
    /**
     * Toggle the visibility of one specific panel by id (e.g. "files",
     * "terminal", "notes"). Smart-toggles via `usePanelActions`: opens
     * a hidden zone, switches the active panel inside a zone, or
     * closes the zone if the panel is already active and visible.
     */
    togglePanel: (panelId: string) => void;
    setTheme: (mode: AppearanceMode) => void;
    focusChatInput: () => void;
    showChatSearch: () => void;
    jumpChatToBottom: () => void;
    /** Cycle to the next/previous workspace tab. Wraps `next_tab` / `previous_tab`. */
    nextWorkspaceTab: () => void;
    previousWorkspaceTab: () => void;
    /** Cycle to the next/previous agent within the current workspace. */
    nextAgent: () => void;
    previousAgent: () => void;
    /**
     * Create a new agent in the current workspace (inheriting the active
     * agent's model) and navigate to it. Delegates to the same handler the
     * `+` tab button and the `new_agent` keybinding use, registered by
     * `AgentTabs`. No-op when no workspace is mounted.
     */
    createAgent: () => void;
    /** Open the Report a problem (file a bug) popover. */
    openReportProblem: () => void;
    /**
     * Clear the active terminal tab's visible buffer and scrollback. No-op
     * when no terminal panel is mounted or no terminal tab has registered
     * itself as the active one.
     */
    clearActiveTerminal: () => void;
  };
  config: {
    /**
     * Update a user-config field. Commands that need the *current* config
     * value should read it via `runtime.store.get(userConfigAtom)` rather
     * than through the runtime — that lets us avoid rebuilding the runtime
     * (and re-registering all builtin commands) on every config change.
     */
    updateField: (field: UserConfigField, value: unknown) => Promise<unknown>;
  };
  electron: {
    isAvailable: boolean;
    reloadWindow: () => void;
  };
};
