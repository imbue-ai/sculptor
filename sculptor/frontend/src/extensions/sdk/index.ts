/**
 * Public SDK barrel. The shape of this module is the contract extension
 * authors target. Changes here are breaking changes to the extension API
 * and must bump the SDK major version.
 */
import type { ExtensionHostApi, ExtensionManifest, ExtensionPanelDefinition } from "../types.ts";

export { openExternal } from "./actions.ts";
export { Markdown, PanelHeader } from "./components.ts";
export type { CurrentWorkspace, NewWorkspaceModalOptions, WorkspaceView } from "./hooks.ts";
export {
  useCurrentWorkspace,
  useExtensionSetting,
  useExtensionSettings,
  useNavigateToWorkspace,
  useOpenNewWorkspaceModal,
  usePluginSetting,
  usePluginSettings,
  useSetExtensionSetting,
  useSetPluginSetting,
  useWorkspaces,
  useWorkspaceTasks,
} from "./hooks.ts";
export type { CodingAgentTaskView } from "~/api";
// The contract an extension's `activate(api)` targets. Re-exported as types so
// extensions reference the host's real definitions instead of hand-redeclaring
// the registration shape (types are erased at build, so no runtime stub).
export type {
  ExtensionHostApi,
  ExtensionManifest,
  HomeViewDefinition,
  OverlayDefinition,
  WorkspaceWidgetDefinition,
} from "../types.ts";
export type { ExtensionPanelDefinition };

/**
 * @deprecated Use {@link ExtensionPanelDefinition}. Kept as an alias so existing
 * extensions that import the old name still type-check; the section shell ignores
 * the legacy zone fields.
 */
export type PanelDefinition = ExtensionPanelDefinition;

// Type aliases under the SDK's pre-rename names ("plugin"), kept so extensions
// authored against that vocabulary still type-check. Types are erased at build,
// so no runtime stub entry is needed for these.
/** @deprecated Use {@link ExtensionManifest}. */
export type PluginManifest = ExtensionManifest;
/** @deprecated Use {@link ExtensionHostApi}. */
export type PluginHostApi = ExtensionHostApi;
/** @deprecated Use {@link ExtensionPanelDefinition}. */
export type PluginPanelDefinition = ExtensionPanelDefinition;
