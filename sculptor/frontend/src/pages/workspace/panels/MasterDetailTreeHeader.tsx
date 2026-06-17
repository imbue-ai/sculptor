import { DropdownMenu, IconButton } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { ChevronsDownUp, List, ListTree, MoreHorizontal, Search } from "lucide-react";
import type { ChangeEvent, ReactElement } from "react";
import { useCallback } from "react";

import { ElementIds } from "~/api";

import { fileBrowserStateAtomFamily, setSearchAtom } from "./fileBrowser/atoms.ts";
import type { ViewMode } from "./fileBrowser/types.ts";
import styles from "./MasterDetailTreeHeader.module.scss";

/** Per-panel configuration for the tree controls. The view-options live in the
 *  diff header's "…" menu (merged); only `hasSearch` affects the tree side. */
export type MasterDetailHeaderConfig = {
  /** Show the always-visible search input (Files / Changes; false for Commits). */
  hasSearch: boolean;
  /** Collapse-all handler and the label shown in the "…" menu. */
  onCollapseAll: () => void;
  collapseLabel: string;
  /** Tree/flat view-mode toggle — Files / Changes only; omit for Commits. */
  viewMode?: ViewMode;
  onToggleViewMode?: () => void;
};

type TreeOptions = Omit<MasterDetailHeaderConfig, "hasSearch">;

/**
 * The search-only header above the tree (Files / Changes). Its height matches
 * the diff viewer's `DiffFileHeader` so the two line up. Commits has no search,
 * so `MasterDetailPanel` skips rendering this for that panel.
 */
export const MasterDetailTreeHeader = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const searchQuery = useAtomValue(fileBrowserStateAtomFamily(workspaceId)).searchQuery;
  const setSearch = useSetAtom(setSearchAtom);

  const handleSearchChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>): void => {
      setSearch({ workspaceId, query: e.target.value, open: true });
    },
    [setSearch, workspaceId],
  );

  return (
    <div className={styles.header}>
      <div className={styles.search}>
        <Search size={14} className={styles.searchIcon} />
        <input
          type="text"
          className={styles.searchInput}
          placeholder="Search files…"
          value={searchQuery}
          onChange={handleSearchChange}
          data-testid={ElementIds.FILE_BROWSER_SEARCH_INPUT}
        />
      </div>
    </div>
  );
};

/**
 * The tree view-options as bare dropdown items — merged into the diff header's
 * "…" menu (passed as `menuLeadingItems`) so there is a single options menu.
 */
export const TreeOptionsItems = ({
  viewMode,
  onToggleViewMode,
  onCollapseAll,
  collapseLabel,
}: TreeOptions): ReactElement => (
  <>
    {onToggleViewMode && (
      <DropdownMenu.Item onSelect={onToggleViewMode}>
        {viewMode === "tree" ? <List size={14} /> : <ListTree size={14} />}
        {viewMode === "tree" ? "Flat list" : "Tree view"}
      </DropdownMenu.Item>
    )}
    <DropdownMenu.Item onSelect={onCollapseAll} data-testid={ElementIds.FILE_BROWSER_COLLAPSE_FOLDERS_BTN}>
      <ChevronsDownUp size={14} /> {collapseLabel}
    </DropdownMenu.Item>
  </>
);

/**
 * Standalone "…" dropdown holding the tree options — used in the empty-detail
 * header, where there is no diff "…" to merge into.
 */
export const TreeOptionsMenu = (props: TreeOptions): ReactElement => (
  <DropdownMenu.Root>
    <DropdownMenu.Trigger>
      <IconButton variant="ghost" size="1" color="gray" aria-label="View options">
        <MoreHorizontal size={14} />
      </IconButton>
    </DropdownMenu.Trigger>
    <DropdownMenu.Content>
      <TreeOptionsItems {...props} />
    </DropdownMenu.Content>
  </DropdownMenu.Root>
);
