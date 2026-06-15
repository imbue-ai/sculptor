/**
 * Public SDK barrel. The shape of this module is the contract plugin
 * authors target. Changes here are breaking changes to the plugin API
 * and must bump the SDK major version.
 */
export { PanelHeader } from "./components.ts";
export {
  useCurrentWorkspaceId,
  usePluginSetting,
  useWorkspaceBranch,
  useWorkspaceId,
  useWorkspaces,
  useWorkspaceTasks,
} from "./hooks.ts";
export type { CodingAgentTaskView, Workspace } from "~/api";
