import { DropdownMenu, IconButton } from "@radix-ui/themes";
import { ChevronsDownUp, List, ListTree, MoreHorizontal, Search, SplitSquareHorizontal } from "lucide-react";
import type { ReactElement } from "react";
import { Fragment } from "react";

import { ElementIds } from "~/api";
import type { FileContextMenuContext } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { useFileMenuGroups } from "~/pages/workspace/panels/fileBrowser/useFileMenuGroups.tsx";

import type { DiffViewOptions, TreeViewOptions } from "./types.ts";

/** The tree (list) view controls — flat/tree + collapse-all (FCC-07). */
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

/** The diff view controls relocated from the old toolbar (FCC-07): find,
 *  split/unified, wrap, and (for markdown) render. */
const DiffViewOptionItems = ({ isBinary, options }: { isBinary: boolean; options: DiffViewOptions }): ReactElement => (
  <>
    {!isBinary && (
      <>
        {/* Find-in-file walks the source DOM, so it is unavailable while markdown
            is rendered (FCC-07 preserves the old toolbar's behavior). */}
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
    <DropdownMenu.CheckboxItem
      checked={options.lineWrapping === "wrap"}
      onCheckedChange={() => options.onToggleLineWrapping()}
      data-testid={ElementIds.DIFF_LINE_WRAP_TOGGLE}
    >
      Wrap lines
    </DropdownMenu.CheckboxItem>
    {options.showRenderToggle && (
      <DropdownMenu.CheckboxItem
        checked={options.isRendered}
        disabled={!options.isRenderToggleEnabled}
        onCheckedChange={() => options.onToggleRender()}
        data-testid={ElementIds.DIFF_RENDER_TOGGLE}
      >
        Render markdown
      </DropdownMenu.CheckboxItem>
    )}
  </>
);

type DiffViewerMenuProps = {
  workspaceId: string;
  /** File-actions context (open/copy/close-tab); when absent only view/tree
   *  options are shown (e.g. the empty state has no file). */
  fileContext: FileContextMenuContext | null;
  /** The relocated diff view controls (FCC-07); absent for non-diff selections. */
  viewOptions?: DiffViewOptions;
  /** The list view controls merged in from the tree side (FCC-07). */
  treeOptions?: TreeViewOptions;
  isBinary: boolean;
};

/**
 * The single triple-dot menu in the viewer header (FCC-07). It assembles, in
 * order: the tree (list) view options, the diff view options that used to sit
 * as toolbar icons, and the per-file actions (open / copy / close tab). The
 * trigger carries {@link ElementIds.DIFF_FILE_HEADER_MENU_TRIGGER}; the
 * relocated toggles re-anchor under it.
 */
export const DiffViewerMenu = ({
  workspaceId,
  fileContext,
  viewOptions,
  treeOptions,
  isBinary,
}: DiffViewerMenuProps): ReactElement => {
  const fileMenuGroups = useFileMenuGroups({ context: fileContext ?? EMPTY_CONTEXT, workspaceId });
  const hasFileActions = fileContext !== null && fileMenuGroups.length > 0;
  const hasTreeOptions = treeOptions !== undefined;
  const hasViewOptions = viewOptions !== undefined;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <IconButton variant="ghost" size="1" color="gray" data-testid={ElementIds.DIFF_FILE_HEADER_MENU_TRIGGER}>
          <MoreHorizontal size={14} />
        </IconButton>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content size="1">
        {hasTreeOptions && <TreeOptionItems options={treeOptions} />}
        {hasViewOptions && (
          <>
            {hasTreeOptions && <DropdownMenu.Separator />}
            <DiffViewOptionItems isBinary={isBinary} options={viewOptions} />
          </>
        )}
        {hasFileActions &&
          fileMenuGroups.map((group, groupIndex) => (
            <Fragment key={group[0].key}>
              {(groupIndex > 0 || hasTreeOptions || hasViewOptions) && <DropdownMenu.Separator />}
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
