/**
 * Public SDK barrel. The shape of this module is the contract plugin
 * authors target. Changes here are breaking changes to the plugin API
 * and must bump the SDK major version.
 */
export { PanelHeader } from "./components.ts";
export { useTaskArtifact, useWorkspaceId, useWorkspaceTasks } from "./hooks.ts";
// TODO(plugins): UsageArtifact was removed from the host API. The
// workspace-cost-tracker plugin still wants cost/token data — re-export
// whatever artifact replaces it once that data path lands.
export type { CodingAgentTaskView, Task, TaskListArtifact } from "~/api";
export { ArtifactType } from "~/api";
