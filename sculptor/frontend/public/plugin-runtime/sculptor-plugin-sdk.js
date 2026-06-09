const host = window.__SCULPTOR_HOST__;
if (!host || !host.sdk) {
  throw new Error("Sculptor plugin runtime: window.__SCULPTOR_HOST__.sdk missing.");
}
const sdk = host.sdk;

// Hooks
export const useWorkspaceTasks = sdk.useWorkspaceTasks;
export const useTaskArtifact = sdk.useTaskArtifact;
export const useWorkspaceId = sdk.useWorkspaceId;
export const useWorkspaceBranch = sdk.useWorkspaceBranch;
export const usePluginSetting = sdk.usePluginSetting;

// Components (re-exports from host)
export const PanelHeader = sdk.PanelHeader;

// Constants / enums
export const ArtifactType = sdk.ArtifactType;
