import { ExternalLink, GitCommitVertical, GitPullRequestArrow, Pencil, Trash2, X, XCircle } from "lucide-react";

import { ElementIds } from "../../../api";
import type { WorkspaceAction, WorkspaceActionRuntime } from "./types.ts";

/**
 * Single source of truth for workspace context actions. Both the
 * right-click context menu (`<WorkspaceContextMenuContent />`) and the
 * command palette (`workspaceActionsProvider` dynamic provider) consume
 * this list. Adding a new entry here surfaces it in both places.
 *
 * Order grouping (top → bottom): git/repo work (most-frequent) → naming
 * → tab navigation (palette only) → close/destroy. The right-click menu
 * renders descriptors in array order; the palette sub-page sorts by the
 * `paletteOrder` number on each descriptor (with non-descriptor rows like
 * "Open in..." interleaved at their own order — see dynamic/workspaceActions).
 */
export const buildWorkspaceActions = (runtime: WorkspaceActionRuntime): ReadonlyArray<WorkspaceAction> => [
  {
    id: "commit",
    title: "Commit changes",
    icon: GitCommitVertical,
    paletteSubtitle: "Stage and commit current changes",
    paletteOrder: 10,
    paletteKeywords: ["git", "save"],
    disabled: (ws): boolean => !runtime.hasUncommittedChanges(ws),
    disabledReason: (): string => "No uncommitted changes",
    perform: (ws): void => runtime.commitChanges(ws),
  },
  {
    id: "create_pr",
    title: "Create pull request",
    icon: GitPullRequestArrow,
    paletteSubtitle: "Push and open a new pull request",
    paletteOrder: 20,
    paletteKeywords: ["pr", "pull", "request", "github"],
    disabled: (ws): boolean => !runtime.canCreatePr(ws),
    disabledReason: (): string => "An open pull request already exists",
    perform: (ws): void => runtime.createMergeRequest(ws),
  },
  {
    id: "open_pr",
    title: "Open pull request",
    icon: ExternalLink,
    paletteSubtitle: "Open the existing pull request in your browser",
    paletteOrder: 30,
    paletteKeywords: ["pr", "pull", "request", "browser", "view", "github"],
    disabled: (ws): boolean => !runtime.hasOpenPr(ws),
    disabledReason: (): string => "No open pull request for this workspace",
    perform: (ws): void => runtime.openMergeRequest(ws),
  },
  // Right-click menu injects "Open in..." submenu here (after open_pr)
  // via `injectAfter` in menu.tsx. The palette sub-page emits its
  // equivalent page-opener at `order: 40` — see dynamic/workspaceActions.
  {
    id: "rename",
    title: "Rename workspace",
    icon: Pencil,
    separatorBefore: true,
    testId: ElementIds.TAB_CONTEXT_MENU_RENAME,
    paletteOrder: 50,
    paletteTitleSuffix: "name",
    perform: (ws): void => runtime.beginRename(ws),
  },
  {
    id: "close",
    title: "Close workspace",
    icon: X,
    separatorBefore: true,
    testId: ElementIds.TAB_CONTEXT_MENU_CLOSE,
    paletteSubtitle: "Close this workspace tab",
    paletteOrder: 80,
    paletteKeywords: ["current", "tab"],
    paletteShortcut: "close_workspace",
    perform: (ws): void => runtime.closeWorkspace(ws),
  },
  {
    id: "close_others",
    title: "Close other workspaces",
    icon: XCircle,
    visible: (): boolean => runtime.canCloseOthers(),
    testId: ElementIds.TAB_CONTEXT_MENU_CLOSE_OTHERS,
    paletteSubtitle: "Close all workspace tabs except this one",
    paletteOrder: 90,
    perform: (ws): void => runtime.closeOtherWorkspaces(ws),
  },
  {
    id: "close_all",
    title: "Close all workspaces",
    icon: XCircle,
    testId: ElementIds.TAB_CONTEXT_MENU_CLOSE_ALL,
    paletteSubtitle: "Close every workspace tab",
    paletteOrder: 100,
    perform: (): void => runtime.closeAllWorkspaces(),
  },
  {
    id: "delete",
    title: "Delete workspace",
    icon: Trash2,
    destructive: true,
    separatorBefore: true,
    testId: ElementIds.TAB_CONTEXT_MENU_DELETE,
    paletteSubtitle: "Permanently delete this workspace",
    paletteOrder: 110,
    paletteTitleSuffix: "name",
    paletteShortcut: "delete_workspace",
    perform: (ws): void => runtime.beginDelete(ws),
  },
];
