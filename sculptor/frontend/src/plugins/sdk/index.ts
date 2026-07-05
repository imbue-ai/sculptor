/**
 * Public SDK barrel. The shape of this module is the contract plugin
 * authors target. Changes here are breaking changes to the plugin API
 * and must bump the SDK major version.
 */
import type { PluginPanelDefinition } from "../contract.ts";

export { openExternal } from "./actions.ts";
export { Markdown, PanelHeader } from "./components.ts";
export type { CurrentWorkspace, WorkspaceView } from "./hostHooks.ts";
export {
  useCurrentWorkspace,
  useNavigateToWorkspace,
  usePluginSetting,
  usePluginSettings,
  useWorkspaces,
  useWorkspaceTasks,
} from "./hostHooks.ts";
export type { CodingAgentTaskView } from "~/api";
// The contract a plugin's `activate(api)` targets. Re-exported as types so
// plugins reference the host's real definitions instead of hand-redeclaring
// the registration shape (types are erased at build, so no runtime stub).
export type {
  HomeViewDefinition,
  OverlayDefinition,
  PluginHostApi,
  PluginManifest,
  WorkspaceWidgetDefinition,
} from "../contract.ts";
export type { PluginPanelDefinition };

/**
 * @deprecated Use {@link PluginPanelDefinition}. Kept as an alias so existing
 * plugins that import the old name still type-check; the section shell ignores
 * the legacy zone fields.
 */
export type PanelDefinition = PluginPanelDefinition;
