import { useSetAtom, useStore } from "jotai";
import { useCallback } from "react";

import { updateWorkspace } from "~/api";
import { workspaceRenameErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { asLiveWorkspace, workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { ToastType } from "~/components/Toast.tsx";

/**
 * Optimistically rename a workspace: show the new name immediately and let the
 * WebSocket frame reconcile with the server-authoritative value; roll back and
 * surface a prominent toast (workspaceRenameErrorToastAtom, rendered by
 * AppShell on every layout) if the write is rejected, so a rename never fails
 * silently. The ONE rename path — every rename surface (desktop sidebar,
 * mobile drawer, mobile workspace header) goes through here so their
 * optimistic/rollback behavior can't drift apart.
 *
 * Returned callback is reference-stable (memoized row components depend on it).
 */
export const useWorkspaceRename = (): ((workspaceId: string, newName: string) => void) => {
  const store = useStore();
  const setRenameErrorToast = useSetAtom(workspaceRenameErrorToastAtom);

  return useCallback(
    (workspaceId: string, newName: string): void => {
      const workspaceAtom = workspaceAtomFamily(workspaceId);
      // A tombstoned (deleting) entry has no live model to rename optimistically;
      // the PATCH still goes out and the server stays authoritative.
      const previous = asLiveWorkspace(store.get(workspaceAtom));
      if (previous !== null) {
        store.set(workspaceAtom, { ...previous, description: newName });
      }
      updateWorkspace({
        path: { workspace_id: workspaceId },
        body: { description: newName },
      }).catch((error: unknown) => {
        console.error("Failed to rename workspace:", error);
        if (previous !== null) {
          store.set(workspaceAtom, previous);
        }
        setRenameErrorToast({
          title: `Failed to rename "${previous?.description ?? "workspace"}"`,
          description: "The name has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: null,
        });
      });
    },
    [store, setRenameErrorToast],
  );
};
