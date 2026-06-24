/**
 * Pseudo-tab IDs for non-workspace surfaces that share the workspace tab
 * bar (Home, Settings). Hoisted out of `WorkspaceTabs.tsx` so the shared
 * `useWorkspaceTabActions` hook can import them without pulling in the
 * component module.
 */
export const HOME_TAB_ID = "__home__";
export const SETTINGS_TAB_ID = "__settings__";
