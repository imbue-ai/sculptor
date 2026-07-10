import { createContext, useContext } from "react";

/**
 * Provided by the host around any extension component that is mounted inside a
 * workspace. Lets the SDK's hooks (e.g. `useWorkspaceTasks`) read the current
 * workspace id without the extension author having to thread it through props.
 */
type WorkspaceExtensionContextValue = {
  workspaceId: string;
};

export const WorkspaceExtensionContext = createContext<WorkspaceExtensionContextValue | null>(null);

export const useWorkspaceExtensionContext = (): WorkspaceExtensionContextValue => {
  const ctx = useContext(WorkspaceExtensionContext);
  if (!ctx) {
    throw new Error(
      "Extension SDK: useWorkspaceTasks called outside a workspace extension mount. It requires the host's " +
        "WorkspaceExtensionContext provider in the component tree (use useCurrentWorkspace in an overlay).",
    );
  }
  return ctx;
};
