import { ScrollArea, Spinner } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement, RefObject } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { RecentWorkspaceResponse } from "../../../api";
import { listRecentWorkspaces } from "../../../api";
import { deletedWorkspaceIdsAtom } from "../../../common/state/atoms/workspaces.ts";
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
  const [workspaces, setWorkspaces] = useState<Array<RecentWorkspaceResponse>>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const areaRef = useRef<HTMLDivElement>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);

  const deletedIds = useAtomValue(deletedWorkspaceIdsAtom);

  const handleNavigateAfterDelete = useCallback((workspaceId: string): void => {
    setWorkspaces((prev) => prev.filter((ws) => ws.objectId !== workspaceId));
  }, []);

  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    onNavigateAfterDelete: handleNavigateAfterDelete,
  });

  const handleDelete = useCallback((workspace: RecentWorkspaceResponse): void => {
    setDeleteTarget({ id: workspace.objectId, name: workspace.description });
  }, []);

  const handleDeleteConfirm = useCallback((): void => {
    if (!deleteTarget) return;
    executeDelete(deleteTarget.id, deleteTarget.name);
    setDeleteTarget(null);
  }, [deleteTarget, executeDelete]);

  // Fetch the recent workspaces once on mount. `isLoading` starts true, so the
  // loading state is already correct without a synchronous setState here; the
  // ignore flag prevents a stale write if the component unmounts mid-request.
  useEffect(() => {
    let isIgnored = false;

    void (async (): Promise<void> => {
      try {
        // Read-only fetch consumed straight from the response body, so the
        // unified-stream acknowledgment adds nothing here. Waiting for it would
        // also fail this load spuriously: the Home page often mounts right as the
        // stream reconnects (the first-run gate remounts AppShell when the
        // workspace list transitions empty <-> non-empty), and an ack for a
        // request in flight across a reconnect never arrives — the tracker would
        // time out and leave the list empty even though the data landed.
        const response = await listRecentWorkspaces({ meta: { skipWsAck: true } });
        if (!isIgnored && response.data) {
          setWorkspaces(response.data.workspaces);
        }
      } catch (error) {
        console.error("Failed to load workspaces:", error);
      } finally {
        if (!isIgnored) {
          setIsLoading(false);
        }
      }
    })();

    return (): void => {
      isIgnored = true;
    };
  }, []);

  const enrichedWorkspaces = useMemo(
    () => workspaces.filter((ws) => !deletedIds.has(ws.objectId)),
    [workspaces, deletedIds],
  );

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
        if (workspace) {
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
  }, [focusedIndex, visibleWorkspaces, onWorkspaceClick, searchInputRef, onEscapeToTitle]);

  // Scroll focused row into view
  useEffect(() => {
    if (focusedIndex !== null) {
      const rows = areaRef.current?.querySelectorAll("[data-workspace-row]");
      rows?.[focusedIndex]?.scrollIntoView({ block: "nearest" });
    }
  }, [focusedIndex]);

  if (isLoading) {
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
