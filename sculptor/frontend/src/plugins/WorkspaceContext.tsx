import { createContext, useContext } from "react";

/**
 * Provided by the host around any plugin component that is mounted inside a
 * workspace. Lets the SDK's hooks (e.g. `useWorkspaceTasks`) read the current
 * workspace id without the plugin author having to thread it through props.
 */
type WorkspacePluginContextValue = {
  workspaceId: string;
};

export const WorkspacePluginContext = createContext<WorkspacePluginContextValue | null>(null);

export const useWorkspacePluginContext = (): WorkspacePluginContextValue => {
  const ctx = useContext(WorkspacePluginContext);
  if (!ctx) {
    throw new Error(
      "Plugin SDK: useWorkspaceTasks / useWorkspaceId / useWorkspaceBranch called outside a workspace " +
        "plugin mount. These hooks require the host's WorkspacePluginContext provider in the component tree.",
    );
  }
  return ctx;
};
