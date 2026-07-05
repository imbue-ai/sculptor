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
    toWorkspace: (workspaceId: string) => void;
    toAgent: (workspaceId: string, agentId: string) => void;
  };
  /**
   * Open the global new-workspace dialog. Mounted globally and the sanctioned
   * create surface, so palette/keyboard entry points open it rather than
   * navigating away to a standalone page.
   */
  openNewWorkspaceDialog: () => void;
  ui: {
    toggleHelpDialog: () => void;
    toggleDevPanel: () => void;
    /**
     * Expand or collapse the left / bottom / right section of the workspace shell.
     * Wraps `toggleSectionAtom`; center never collapses.
     */
    toggleLeftPanel: () => void;
    toggleBottomPanel: () => void;
    toggleRightPanel: () => void;
    /** Collapse or expand the workspace nav sidebar (wraps `sidebarCollapsedAtom`). */
    toggleSidebar: () => void;
    /** Maximize the active section, or restore if one is already maximized. */
    toggleMaximizeSection: () => void;
    setTheme: (mode: AppearanceMode) => void;
    focusChatInput: () => void;
    showChatSearch: () => void;
    jumpChatToBottom: () => void;
    /** Cycle to the next/previous workspace. Wraps the `next_tab` / `previous_tab` keybindings. */
    nextWorkspaceTab: () => void;
    previousWorkspaceTab: () => void;
    /** Cycle to the next/previous agent within the current workspace. */
    nextAgent: () => void;
    previousAgent: () => void;
    /**
     * Create a new agent in the current workspace (inheriting the active
     * agent's model) and navigate to it. Delegates to the same handler the
     * add-panel `+` and the `new_agent` keybinding use, registered by
     * `useWorkspaceShellBootstrap`. No-op when no workspace is mounted.
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
