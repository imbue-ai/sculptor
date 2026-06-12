import { Button, Popover, Spinner } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { RecentWorkspaceResponse } from "~/api";
import { ElementIds, listRecentWorkspaces } from "~/api";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { closedWorkspaceIdsAtom, openWorkspaceTabAtom } from "~/common/state/atoms/workspaces.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";

import { ClosedWorkspaceRow } from "./ClosedWorkspaceRow.tsx";
import styles from "./ClosedWorkspacesPill.module.scss";
import { DeleteConfirmationDialog } from "./DeleteConfirmationDialog.tsx";
import { popoverFriendlyModalGuard } from "./popoverFriendlyModal.ts";

export const ClosedWorkspacesPill = (): ReactElement | null => {
  const closedWorkspaceIds = useAtomValue(closedWorkspaceIdsAtom);
  const openWorkspaceTab = useSetAtom(openWorkspaceTabAtom);
  const { navigateToWorkspace } = useImbueNavigate();

  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [workspaces, setWorkspaces] = useState<Array<RecentWorkspaceResponse>>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    onNavigateAfterDelete: (): void => {
      // No navigation needed — workspace is already closed (not the active tab)
    },
  });

  const handleOpenChange = useCallback((open: boolean): void => {
    setIsOpen(open);
  }, []);

  // The dropdown rows come from `listRecentWorkspaces()` (denormalized
  // project_name / agent_count / last_activity_at aren't on the streamed
  // Workspace), but the pill count comes from `closedWorkspaceIdsAtom`.
  // Two truth sources race: `pendingCloseWorkspaceIdsAtom` flips the
  // pill immediately, while the fetch can land before the close-PATCH
  // commits and return a stale list — the dropdown then disagrees with
  // the pill.  Re-fetch whenever the closed-id set changes while the
  // popover is open so the two converge.  See SCU-487 for the
  // structural fix that would let us drop the fetch entirely.
  //
  // Coordination uses a snapshot+last-fetched key:
  //
  //   * `isFetchingRef` keeps at most one request in flight; concurrent
  //     calls are skipped, never stacked.  Under H/2, a burst of
  //     workspace updates would otherwise fire many parallel fetches.
  //   * `lastFetchedKey` records the closed-id set the in-flight fetch
  //     was started for.  When a coalesced caller arrives during the
  //     fetch, the in-flight one completes and stores its (now stale)
  //     snapshot — the effect then re-runs because `lastFetchedKey`
  //     changed, sees the drift, and fires another fetch.  No data is
  //     lost; we may render the stale list for one frame.
  //   * `cancelledRef` is flipped on unmount so the post-`await`
  //     setStates become no-ops on a torn-down tree.  React 18 silences
  //     the warning, but this keeps the lifecycle explicit.
  const closedIdsKey = closedWorkspaceIds.join(",");
  const [lastFetchedKey, setLastFetchedKey] = useState<string | null>(null);
  const isFetchingRef = useRef<boolean>(false);
  const cancelledRef = useRef<boolean>(false);

  useEffect(() => {
    // Reset on (re)mount so React 18 StrictMode's simulated unmount-remount
    // cycle in dev mode can't leave cancelledRef stuck at `true`. Without
    // this, the cleanup fires once during strict-mode dev, the remount
    // re-uses the same ref, and the next fetch returns early — the spinner
    // never resolves because the `setIsLoading(false)` is gated on
    // `!cancelledRef.current`.
    cancelledRef.current = false;
    return (): void => {
      cancelledRef.current = true;
    };
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    if (closedIdsKey === lastFetchedKey) return;
    if (isFetchingRef.current) return;

    isFetchingRef.current = true;
    setIsLoading(true);
    const snapshot = closedIdsKey;
    void (async (): Promise<void> => {
      try {
        const response = await listRecentWorkspaces();
        if (cancelledRef.current) return;
        if (response.data) {
          setWorkspaces(response.data.workspaces);
          setLastFetchedKey(snapshot);
        }
      } finally {
        isFetchingRef.current = false;
        if (!cancelledRef.current) setIsLoading(false);
      }
    })();
  }, [isOpen, closedIdsKey, lastFetchedKey]);

  const handleOpenAll = useCallback((): void => {
    closedWorkspaceIds.forEach((id) => {
      openWorkspaceTab(id);
    });
    setIsOpen(false);
  }, [closedWorkspaceIds, openWorkspaceTab]);

  const handleReopen = useCallback(
    (workspaceId: string): void => {
      openWorkspaceTab(workspaceId);
      navigateToWorkspace(workspaceId);
      setIsOpen(false);
    },
    [openWorkspaceTab, navigateToWorkspace],
  );

  const handleDeleteRequest = useCallback((workspace: RecentWorkspaceResponse): void => {
    setDeleteTarget({ id: workspace.objectId, name: workspace.description ?? workspace.objectId });
  }, []);

  const handleDeleteConfirm = useCallback((): void => {
    if (deleteTarget) {
      executeDelete(deleteTarget.id, deleteTarget.name);
      setWorkspaces((prev) => prev.filter((ws) => ws.objectId !== deleteTarget.id));
      setDeleteTarget(null);
    }
  }, [deleteTarget, executeDelete]);

  if (closedWorkspaceIds.length === 0) {
    return null;
  }

  const closedIdSet = new Set(closedWorkspaceIds);
  const closedWorkspaces = workspaces
    .filter((ws) => closedIdSet.has(ws.objectId))
    .sort((a, b) => {
      const aTime = a.lastActivityAt ?? "";
      const bTime = b.lastActivityAt ?? "";
      return bTime.localeCompare(aTime);
    });

  return (
    <>
      <Popover.Root open={isOpen} onOpenChange={handleOpenChange}>
        <Popover.Trigger>
          <Button variant="ghost" size="1" className={styles.pill} data-testid={ElementIds.CLOSED_WORKSPACES_PILL}>
            Closed {closedWorkspaceIds.length}
            <ChevronDown size={14} />
          </Button>
        </Popover.Trigger>
        <Popover.Content
          side="bottom"
          align="end"
          sideOffset={8}
          className={styles.dropdown}
          data-testid={ElementIds.CLOSED_WORKSPACES_DROPDOWN}
          {...popoverFriendlyModalGuard}
        >
          <div className={styles.header}>
            <span className={styles.title}>Closed workspaces</span>
            <Button
              variant="ghost"
              size="1"
              onClick={handleOpenAll}
              data-testid={ElementIds.CLOSED_WORKSPACES_OPEN_ALL_BUTTON}
            >
              Open all
            </Button>
          </div>
          <div className={styles.scrollArea}>
            {isLoading && workspaces.length === 0 ? (
              <Spinner m="4" />
            ) : (
              // Render stale rows during background refreshes so we don't
              // unmount/remount the list on every closed-id change — that
              // detaches the row DOM mid-click in tests and causes flicker.
              closedWorkspaces.map((ws) => (
                <ClosedWorkspaceRow
                  key={ws.objectId}
                  workspace={ws}
                  onReopen={handleReopen}
                  onDelete={handleDeleteRequest}
                />
              ))
            )}
          </div>
        </Popover.Content>
      </Popover.Root>
      <DeleteConfirmationDialog
        isOpen={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        entityType="workspace"
        entityName={deleteTarget?.name ?? ""}
        onConfirm={handleDeleteConfirm}
      />
    </>
  );
};
