import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { workspacesArrayAtom } from "~/common/state/atoms/workspaces";
import { isElectron } from "~/electron/utils";

import { browserViewRegistryAtom } from "./browserViewRegistry";
import { BrowserViewSlot } from "./BrowserViewSlot";

// Rendered once at the app root, above the router. Hosts every workspace's
// browser <webview> for the lifetime of the app session, so route changes
// (workspace ↔ /settings ↔ /ws/new) never tear down the webContents.
export const BrowserViewHost = (): ReactElement | null => {
  if (!isElectron()) return null;
  return <BrowserViewHostElectron />;
};

const BrowserViewHostElectron = (): ReactElement => {
  const registry = useAtomValue(browserViewRegistryAtom);
  useDeletedWorkspaceCleanup();
  return (
    <>
      {Array.from(registry).map((workspaceId) => (
        <BrowserViewSlot key={workspaceId} workspaceId={workspaceId} />
      ))}
    </>
  );
};

// Evict registry entries whose workspace no longer exists. The webContents
// for a deleted workspace would otherwise leak for the rest of the session.
// We skip eviction while the workspace list is still loading (undefined)
// to avoid tearing down panels during a transient empty state.
const useDeletedWorkspaceCleanup = (): void => {
  const workspaces = useAtomValue(workspacesArrayAtom);
  const setRegistry = useSetAtom(browserViewRegistryAtom);
  useEffect(() => {
    if (workspaces === undefined) return;
    const liveIds = new Set(workspaces.map((ws) => ws.objectId));
    setRegistry((prev) => {
      let hasRemoved = false;
      const next = new Set<string>();
      for (const id of prev) {
        if (liveIds.has(id)) {
          next.add(id);
        } else {
          hasRemoved = true;
        }
      }
      return hasRemoved ? next : prev;
    });
  }, [workspaces, setRegistry]);
};
