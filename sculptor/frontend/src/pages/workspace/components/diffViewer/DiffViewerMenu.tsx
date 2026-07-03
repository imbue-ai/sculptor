import { DropdownMenu, IconButton, Tooltip } from "@radix-ui/themes";
import {
  BookOpen,
  ChevronsDownUp,
  Code,
  List,
  ListTree,
  MoreHorizontal,
  RefreshCw,
  Search,
  SplitSquareHorizontal,
  Text,
  WrapText,
} from "lucide-react";
import type { ReactElement } from "react";
import { Fragment } from "react";

import { ElementIds } from "~/api";
import type { FileContextMenuContext } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { useFileMenuGroups } from "~/pages/workspace/panels/fileBrowser/useFileMenuGroups.tsx";

import type { DiffViewOptions, TreeViewOptions } from "./types.ts";

/** The tree (list) view controls — flat/tree + collapse-all. */
const TreeOptionItems = ({ options }: { options: TreeViewOptions }): ReactElement => (
  <>
    {options.onToggleViewMode && (
      <DropdownMenu.Item
        onSelect={() => options.onToggleViewMode?.()}
        data-testid={ElementIds.DIFF_MENU_TREE_VIEW_MODE}
      >
        {options.viewMode === "tree" ? <List size={14} /> : <ListTree size={14} />}
        {options.viewMode === "tree" ? "Flat list" : "Tree view"}
      </DropdownMenu.Item>
    )}
    <DropdownMenu.Item
      onSelect={() => options.onCollapseAll()}
      data-testid={ElementIds.FILE_BROWSER_COLLAPSE_FOLDERS_BTN}
    >
      <ChevronsDownUp size={14} /> {options.collapseLabel}
    </DropdownMenu.Item>
  </>
);

/** The diff view controls: find, split/unified, wrap, and (for markdown) render. */
const DiffViewOptionItems = ({ isBinary, options }: { isBinary: boolean; options: DiffViewOptions }): ReactElement => (
  <>
    {!isBinary && (
      <>
        {/* Find-in-file walks the source DOM, so it is unavailable while markdown
            is rendered. */}
        {!(options.showRenderToggle && options.isRendered) && (
          <DropdownMenu.Item onSelect={() => options.onToggleSearch()} data-testid={ElementIds.DIFF_FIND_IN_FILE_BTN}>
            <Search size={14} /> Find in file
          </DropdownMenu.Item>
        )}
        <DropdownMenu.Item onSelect={() => options.onToggleViewType()} data-testid={ElementIds.DIFF_SPLIT_VIEW_TOGGLE}>
          <SplitSquareHorizontal size={14} /> {options.viewType === "split" ? "Unified view" : "Split view"}
        </DropdownMenu.Item>
      </>
    )}
    <DropdownMenu.Item onSelect={() => options.onToggleLineWrapping()} data-testid={ElementIds.DIFF_LINE_WRAP_TOGGLE}>
      {options.lineWrapping === "wrap" ? <Text size={14} /> : <WrapText size={14} />}
      {options.lineWrapping === "wrap" ? "Unwrap lines" : "Wrap lines"}
    </DropdownMenu.Item>
    {options.showRenderToggle && (
      <DropdownMenu.Item
        disabled={!options.isRenderToggleEnabled}
        onSelect={() => options.onToggleRender()}
        data-testid={ElementIds.DIFF_RENDER_TOGGLE}
      >
        {options.isRendered ? <Code size={14} /> : <BookOpen size={14} />}
        {options.isRendered ? "Show source" : "Render markdown"}
      </DropdownMenu.Item>
    )}
  </>
);

type DiffViewerMenuProps = {
  workspaceId: string;
  /** File-actions context (open/copy/close-tab); when absent only view/tree
   *  options are shown (e.g. the empty state has no file). */
  fileContext: FileContextMenuContext | null;
  /** The diff view controls; absent for non-diff selections. */
  viewOptions?: DiffViewOptions;
  /** The list view controls merged in from the tree side. */
  treeOptions?: TreeViewOptions;
  /** Manually re-syncs the viewer's data from git (diff / file content). */
  onRefresh?: () => void;
  isBinary: boolean;
};

/**
 * The single triple-dot menu in the viewer header. It assembles, in order:
 * the manual refresh, the tree (list) view options, the diff view options,
 * and the per-file actions (open / copy / close tab). The trigger carries
 * {@link ElementIds.DIFF_FILE_HEADER_MENU_TRIGGER}; the toggles anchor under it.
 */
export const DiffViewerMenu = ({
  workspaceId,
  fileContext,
  viewOptions,
  treeOptions,
  onRefresh,
  isBinary,
}: DiffViewerMenuProps): ReactElement => {
  const fileMenuGroups = useFileMenuGroups({ context: fileContext ?? EMPTY_CONTEXT, workspaceId });
  const hasFileActions = fileContext !== null && fileMenuGroups.length > 0;
  const hasTreeOptions = treeOptions !== undefined;
  const hasViewOptions = viewOptions !== undefined;
  const hasRefresh = onRefresh !== undefined;

  return (
    <DropdownMenu.Root>
      <Tooltip content="View options">
        <DropdownMenu.Trigger>
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            aria-label="View options"
            data-testid={ElementIds.DIFF_FILE_HEADER_MENU_TRIGGER}
          >
            <MoreHorizontal size={14} />
          </IconButton>
        </DropdownMenu.Trigger>
      </Tooltip>
      <DropdownMenu.Content size="1">
        {hasRefresh && (
          <DropdownMenu.Item onSelect={() => onRefresh()}>
            <RefreshCw size={14} /> Refresh
          </DropdownMenu.Item>
        )}
        {hasTreeOptions && (
          <>
            {hasRefresh && <DropdownMenu.Separator />}
            <TreeOptionItems options={treeOptions} />
          </>
        )}
        {hasViewOptions && (
          <>
            {(hasRefresh || hasTreeOptions) && <DropdownMenu.Separator />}
            <DiffViewOptionItems isBinary={isBinary} options={viewOptions} />
          </>
        )}
        {hasFileActions &&
          fileMenuGroups.map((group, groupIndex) => (
            <Fragment key={group[0].key}>
              {(groupIndex > 0 || hasRefresh || hasTreeOptions || hasViewOptions) && <DropdownMenu.Separator />}
              {group.map((item) => (
                <DropdownMenu.Item
                  key={item.key}
                  disabled={item.disabled}
                  onSelect={item.handleSelect}
                  data-testid={item.key}
                >
                  {item.icon}
                  {item.label}
                </DropdownMenu.Item>
              ))}
            </Fragment>
          ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};

// `useFileMenuGroups` must be called unconditionally (rules of hooks), so when
// there is no file selected we pass a placeholder context and simply do not
// render the resulting groups.
const EMPTY_CONTEXT: FileContextMenuContext = {
  filePath: "",
  isFolder: false,
  isBinary: false,
  source: "diff-header",
};
