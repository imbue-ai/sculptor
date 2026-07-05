/**
 * Pseudo-tab IDs for non-workspace surfaces (Home, Settings) that share the
 * workspace tab bar. Kept in a standalone module so the shared
 * `useWorkspaceTabActions` hook can import them without a component
 * dependency.
 */
export const HOME_TAB_ID = "__home__";
export const SETTINGS_TAB_ID = "__settings__";
