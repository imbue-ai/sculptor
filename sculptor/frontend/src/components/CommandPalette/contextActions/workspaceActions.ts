import { ExternalLink, GitCommitVertical, GitPullRequestArrow, Pencil, Trash2 } from "lucide-react";

import { ElementIds } from "../../../api";
import type { WorkspaceAction, WorkspaceActionRuntime } from "./types.ts";

/**
 * Single source of truth for workspace context actions. Both the
 * right-click context menu (`<WorkspaceContextMenuContent />`) and the
 * command palette (`workspaceActionsProvider` dynamic provider) consume
 * this list. Adding a new entry here surfaces it in both places.
 *
 * Order grouping (top → bottom): git/repo work (most-frequent) → naming
 * → destroy. The right-click menu renders descriptors in array order; the
 * palette sub-page sorts by the `paletteOrder` number on each descriptor
 * (with non-descriptor rows like "Open in..." interleaved at their own
 * order — see dynamic/workspaceActions).
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
    // `title` / `paletteSubtitle` / `paletteKeywords` stay stable as
    // fallbacks; the `get*` overrides flip the verb based on the
    // workspace's git provider so users see only their provider's term.
    title: "Create pull request",
    getTitle: (ws): string => (runtime.prTerm(ws) === "merge request" ? "Create merge request" : "Create pull request"),
    icon: GitPullRequestArrow,
    paletteSubtitle: "Push and open a new pull request",
    getPaletteSubtitle: (ws): string =>
      runtime.prTerm(ws) === "merge request" ? "Push and open a new merge request" : "Push and open a new pull request",
    paletteOrder: 20,
    paletteKeywords: ["pr", "pull", "request", "github"],
    // GitHub: pr/pull/github. GitLab: mr/merge/gitlab. "request" is
    // shared so users typing the generic noun still find the row.
    getPaletteKeywords: (ws): ReadonlyArray<string> =>
      runtime.prTerm(ws) === "merge request"
        ? ["mr", "merge", "request", "gitlab"]
        : ["pr", "pull", "request", "github"],
    disabled: (ws): boolean => !runtime.canCreatePr(ws),
    disabledReason: (ws): string => `An open ${runtime.prTerm(ws)} already exists`,
    perform: (ws): void => runtime.createMergeRequest(ws),
  },
  {
    id: "open_pr",
    title: "Open pull request",
    getTitle: (ws): string => (runtime.prTerm(ws) === "merge request" ? "Open merge request" : "Open pull request"),
    icon: ExternalLink,
    paletteSubtitle: "Open the existing pull request in your browser",
    getPaletteSubtitle: (ws): string =>
      runtime.prTerm(ws) === "merge request"
        ? "Open the existing merge request in your browser"
        : "Open the existing pull request in your browser",
    paletteOrder: 30,
    paletteKeywords: ["pr", "pull", "request", "browser", "view", "github"],
    getPaletteKeywords: (ws): ReadonlyArray<string> =>
      runtime.prTerm(ws) === "merge request"
        ? ["mr", "merge", "request", "browser", "view", "gitlab"]
        : ["pr", "pull", "request", "browser", "view", "github"],
    disabled: (ws): boolean => !runtime.hasOpenPr(ws),
    disabledReason: (ws): string => `No open ${runtime.prTerm(ws)} for this workspace`,
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
  // Close-workspace actions were removed: the sidebar shows every workspace
  // regardless of any prior "open tab" state, so closing a workspace no longer
  // hides it and the option had no observable effect.
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
