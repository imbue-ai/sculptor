import { ScrollArea, Spinner } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { useAtomValue, useStore } from "jotai";
import type { ReactElement, RefObject } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { RecentWorkspaceResponse } from "../../../api";
import { listRecentWorkspaces } from "../../../api";
import { queryClient, recentWorkspacesQueryKey } from "../../../common/queryClient.ts";
import { isWorkspaceDeletingAtomFamily, workspaceIdsAtom } from "../../../common/state/atoms/workspaces.ts";
import { useOptimisticWorkspaceDelete } from "../../../common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { DeleteConfirmationDialog } from "../../../components/DeleteConfirmationDialog.tsx";
import { EmptyState } from "./EmptyState.tsx";
import styles from "./RecentWorkspaces.module.scss";
import { WorkspaceRow } from "./WorkspaceRow.tsx";
import { WorkspaceSearchBar } from "./WorkspaceSearchBar.tsx";

const PAGE_SIZE = 25;

type RecentWorkspacesProps = {
  searchInputRef: RefObject<HTMLInputElement | null>;
  autoFocusSearch?: boolean;
  onWorkspaceClick: (workspace: RecentWorkspaceResponse) => void;
  onOpenInNewTab: (workspace: RecentWorkspaceResponse) => void;
  onEscapeToTitle: () => void;
};

export const RecentWorkspaces = ({
  searchInputRef,
  autoFocusSearch,
  onWorkspaceClick,
  onOpenInNewTab,
  onEscapeToTitle,
}: RecentWorkspacesProps): ReactElement => {
  const [searchQuery, setSearchQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const areaRef = useRef<HTMLDivElement>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const store = useStore();

  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    // Deleting from Home stays on Home: the row renders as "Deleting…" until
    // the refreshed list drops it, and a failed delete un-dims it in place.
    onNavigateAfterDelete: useCallback((): void => {}, []),
  });

  const handleDelete = useCallback((workspace: RecentWorkspaceResponse): void => {
    setDeleteTarget({ id: workspace.objectId, name: workspace.description });
  }, []);

  const handleDeleteConfirm = useCallback((): void => {
    if (!deleteTarget) return;
    executeDelete(deleteTarget.id, deleteTarget.name);
    setDeleteTarget(null);
  }, [deleteTarget, executeDelete]);

  // The pulled list snapshot. Data-freshness is invalidation-driven (staleTime
  // is Infinity globally): membership changes below, plus a confirmed delete
  // (the mutation invalidates the key so the list heals even when the stream
  // is down). Refetches swap the list in place — `isPending` is true only
  // before the first data lands, so there is no spinner flash.
  const { data: workspaces, isPending } = useQuery({
    queryKey: recentWorkspacesQueryKey(),
    queryFn: async (): Promise<Array<RecentWorkspaceResponse>> => {
      try {
        // Read-only fetch consumed straight from the response body, so the
        // unified-stream acknowledgment adds nothing here. Waiting for it would
        // also fail this load spuriously: the Home page can mount right as the
        // stream reconnects, and an ack for a request in flight across a
        // reconnect never arrives — the tracker would time out and leave the
        // list empty even though the data landed.
        const response = await listRecentWorkspaces({ meta: { skipWsAck: true } });
        return response.data?.workspaces ?? [];
      } catch (error) {
        // The list renders its empty state when the query errors, which would
        // otherwise silently mask a failed load.
        console.error("Failed to load workspaces:", error);
        throw error;
      }
    },
  });

  // The set of live workspace ids, kept fresh by the unified stream and only
  // rewritten when membership actually changes (updateWorkspacesAtom guards
  // the write), so it is a stable effect dependency. The invalidation fires
  // when membership changes — a workspace created or deleted outside this
  // page (the CLI, another window) must show up without a remount, since
  // Home can stay mounted indefinitely — and on remounts with a loaded store,
  // for freshness.
  const liveWorkspaceIds = useAtomValue(workspaceIdsAtom);

  useEffect(() => {
    // Before the first WS frame there is no membership to sync against, and
    // the mount-time query fetch is already in flight — invalidating here
    // would only duplicate it.
    if (liveWorkspaceIds === undefined) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: recentWorkspacesQueryKey() });
  }, [liveWorkspaceIds]);

  // Rows the canonical store holds as tombstones stay in the list and render
  // as "Deleting…" (see WorkspaceRow) rather than being filtered out — the
  // pending state is visible, and the row leaves the DOM only when the
  // refreshed server list confirms the deletion.
  const enrichedWorkspaces = useMemo(() => workspaces ?? [], [workspaces]);

  const filteredWorkspaces = useMemo(() => {
    if (!searchQuery.trim()) return enrichedWorkspaces;
    const query = searchQuery.toLowerCase();
    return enrichedWorkspaces.filter(
      (ws) =>
        ws.description.toLowerCase().includes(query) ||
        (ws.sourceBranch?.toLowerCase().includes(query) ?? false) ||
        ws.projectName.toLowerCase().includes(query),
    );
  }, [enrichedWorkspaces, searchQuery]);

  const sortedWorkspaces = useMemo(
    () =>
      [...filteredWorkspaces].sort(
        (a, b) => new Date(b.lastActivityAt).getTime() - new Date(a.lastActivityAt).getTime(),
      ),
    [filteredWorkspaces],
  );

  const visibleWorkspaces = useMemo(() => sortedWorkspaces.slice(0, visibleCount), [sortedWorkspaces, visibleCount]);
  const hasMore = visibleCount < sortedWorkspaces.length;

  // Reset focused index and visible count when search query changes. Adjusting
  // during render (comparing against the previous query) avoids the extra render
  // an effect would add.
  const [lastSearchQuery, setLastSearchQuery] = useState(searchQuery);
  if (searchQuery !== lastSearchQuery) {
    setLastSearchQuery(searchQuery);
    setFocusedIndex(null);
    setVisibleCount(PAGE_SIZE);
  }

  // Keyboard navigation within the recent workspaces area
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedIndex((prev) => {
          if (prev === null) return 0;
          return Math.min(prev + 1, visibleWorkspaces.length - 1);
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedIndex((prev) => {
          if (prev === null) {
            // Focus is on the search bar — nothing above to focus.
            return null;
          }

          if (prev === 0) {
            searchInputRef.current?.focus();
            return null;
          }
          return prev - 1;
        });
      } else if (e.key === "Enter" && focusedIndex !== null) {
        e.preventDefault();
        const workspace = visibleWorkspaces[focusedIndex];
        // A row mid-delete is non-interactive: don't navigate into a
        // workspace that is going away.
        if (workspace && !store.get(isWorkspaceDeletingAtomFamily(workspace.objectId))) {
          onWorkspaceClick(workspace);
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        setSearchQuery("");
        setFocusedIndex(null);
        onEscapeToTitle();
      }
    };

    const areaElement = areaRef.current;
    if (areaElement) {
      areaElement.addEventListener("keydown", handleKeyDown);
      return (): void => areaElement.removeEventListener("keydown", handleKeyDown);
    }
  }, [focusedIndex, visibleWorkspaces, onWorkspaceClick, searchInputRef, onEscapeToTitle, store]);

  // Scroll focused row into view
  useEffect(() => {
    if (focusedIndex !== null) {
      const rows = areaRef.current?.querySelectorAll("[data-workspace-row]");
      rows?.[focusedIndex]?.scrollIntoView({ block: "nearest" });
    }
  }, [focusedIndex]);

  if (isPending) {
    return (
      <div className={styles.recentArea}>
        <Spinner size="2" />
      </div>
    );
  }

  if (enrichedWorkspaces.length === 0) {
    return (
      <div className={styles.recentArea}>
        <EmptyState />
      </div>
    );
  }

  return (
    <>
      <div ref={areaRef} className={styles.recentArea} tabIndex={0}>
        <WorkspaceSearchBar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          inputRef={searchInputRef}
          autoFocus={autoFocusSearch}
          onEscape={(): void => {
            setSearchQuery("");
            setFocusedIndex(null);
            onEscapeToTitle();
          }}
        />
        {sortedWorkspaces.length === 0 ? (
          <div className={styles.noResults}>No results for &ldquo;{searchQuery}&rdquo;</div>
        ) : (
          <ScrollArea type="auto" scrollbars="vertical" className={styles.workspaceList}>
            {visibleWorkspaces.map((ws, index) => (
              <WorkspaceRow
                key={ws.objectId}
                workspace={ws}
                isFocused={focusedIndex === index}
                onClick={(e: React.MouseEvent): void => {
                  if (e.metaKey) {
                    onOpenInNewTab(ws);
                  } else {
                    onWorkspaceClick(ws);
                  }
                }}
                onOpenInNewTab={(): void => onOpenInNewTab(ws)}
                onDelete={handleDelete}
              />
            ))}
            {hasMore && (
              <button className={styles.showMoreButton} onClick={(): void => setVisibleCount((n) => n + PAGE_SIZE)}>
                Show more ({sortedWorkspaces.length - visibleCount} remaining)
              </button>
            )}
          </ScrollArea>
        )}
      </div>
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
