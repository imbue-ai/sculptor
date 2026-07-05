import { FolderOpenIcon, SettingsIcon } from "lucide-react";

import { getOpenWithItems, getPreferredApp } from "../../../common/openInApp/items.tsx";
import { workspacesArrayAtom } from "../../../common/state/atoms/workspaces.ts";
import { workspaceActionsTargetAtom } from "../contextActions/atoms/contextActions.ts";
import type { WorkspaceActionRuntime } from "../contextActions/types.ts";
import { buildWorkspaceActions } from "../contextActions/workspaceActions.ts";
import type { Command, DynamicProvider } from "../types/commandPalette.ts";
import type { CommandRuntime } from "../utils/runtime.ts";

const workspaceName = (description: string | undefined): string => (description ?? "").trim() || "Untitled";

/**
 * Surfaces the right-click menu actions for the CURRENT workspace in
 * Cmd+K. Cross-workspace action picking is intentionally not supported.
 *
 * Flow:
 *   "Workspace actions…" (root, primary, only when ctx.activeWorkspaceId)
 *      → workspace.actions  (pick an action for the current workspace)
 *
 * The action list comes from `buildWorkspaceActions`, which is the
 * single source of truth shared with the sidebar's workspace-row menu
 * (`WorkspaceSidebar`).
 */
export const buildWorkspaceActionsProvider = (
  runtime: CommandRuntime,
  actionRuntime: WorkspaceActionRuntime,
): DynamicProvider => ({
  id: "dynamic.workspace_actions",
  produce: (ctx): Array<Command> => {
    if (ctx.activeWorkspaceId == null) return [];
    const workspaces = runtime.store.get(workspacesArrayAtom) ?? [];
    const target = workspaces.find((ws) => ws.objectId === ctx.activeWorkspaceId);
    if (target == null) return [];

    const name = workspaceName(target.description);
    const actions = buildWorkspaceActions(actionRuntime);
    const out: Array<Command> = [];

    out.push({
      id: "workspaces.actions.open",
      title: "Workspace actions...",
      // Workspace name leads the subtitle so when truncation kicks in
      // (long workspace names + descriptions are common), the trailing
      // descriptor gets cut instead of the name. The descriptor is
      // intentionally generic — the action set grows over time, so an
      // explicit verb list goes stale.
      subtitle: `${name} — actions for this workspace`,
      keywords: ["rename", "close", "delete", "manage", "edit", "commit", "pr", name.toLowerCase()],
      group: "workspaces",
      icon: SettingsIcon,
      pageId: "workspace.actions",
      primary: true,
      order: 30,
      perform: () => {
        // Capture the current workspace as the action target before the
        // runner pushes the page. The action sub-page reads this atom to
        // know which workspace to act on.
        runtime.store.set(workspaceActionsTargetAtom, target.objectId);
      },
    });

    // Sub-page sort order is stamped on each descriptor as `paletteOrder`.
    // Open-in (the inline page-opener below) sits at 40 between open_pr
    // (30) and rename (50); next/previous workspace tab at 60/70 (defined
    // in `builtinCommands/workspaces.ts`).
    //
    // Mechanical descriptor → Command projection. All per-action
    // metadata (order, keywords, shortcut, title-suffix policy) lives on
    // the descriptor in `contextActions/workspaceActions.ts` — this loop
    // just consumes it. The workspace name is appended to keywords on
    // every row so fuzzy search matches by name regardless of the
    // descriptor's keyword set.
    for (const action of actions) {
      if (action.visible && !action.visible(target)) continue;
      const baseTitle = action.getTitle ? action.getTitle(target) : action.title;
      const titleSuffix = action.paletteTitleSuffix === "name" ? `: ${name}` : "";
      const isDisabled = action.disabled?.(target) ?? false;
      const reason = isDisabled ? action.disabledReason?.(target) : undefined;
      const baseSubtitle = action.getPaletteSubtitle ? action.getPaletteSubtitle(target) : action.paletteSubtitle;
      const baseKeywords = action.getPaletteKeywords ? action.getPaletteKeywords(target) : action.paletteKeywords;
      out.push({
        id: `workspaces.action.${target.objectId}.${action.id}`,
        title: `${baseTitle}${titleSuffix}`,
        // Disabled rows surface the reason inline as the subtitle —
        // matches the agents.switch precedent (see `agentCommands.ts`)
        // and avoids the discoverability problem of a hover-only tooltip.
        subtitle: reason ?? baseSubtitle,
        keywords: [action.id, ...(baseKeywords ?? []), name.toLowerCase()],
        group: "workspaces",
        icon: action.icon,
        shortcut: action.paletteShortcut,
        onPage: "workspace.actions",
        order: action.paletteOrder,
        disabled: isDisabled,
        perform: () => action.perform(target),
      });
    }

    // Stays in sync with the workspace metadata bar's repo-path dropdown
    // — both consume `getOpenWithItems()` from openInApp/items.ts.
    const openWithItems = getOpenWithItems();
    if (openWithItems.length > 0) {
      const canOpenInOS = actionRuntime.canOpenInOS();
      // Used as the tooltip reason on every Open-in row when the
      // backend doesn't expose the launch endpoint (remote backends).
      const openInDisabledReason = "Opening external apps is unavailable on this backend";

      out.push({
        id: `workspaces.open_in.open.${target.objectId}`,
        title: "Open in...",
        subtitle: "Reveal the repo in Finder, VS Code, a terminal, ...",
        keywords: ["open", "reveal", "finder", "editor", "terminal", "vs code", "cursor"],
        group: "workspaces",
        icon: FolderOpenIcon,
        pageId: "workspace.open_in",
        onPage: "workspace.actions",
        // Sits between Open PR (30) and Rename (50) — keeps the
        // git/repo cluster contiguous before the naming + close groups.
        order: 40,
        // Disabled when the backend can't open paths (remote backend).
        // The row stays put so the user knows the capability exists.
        disabled: !canOpenInOS,
        disabledReason: !canOpenInOS ? openInDisabledReason : undefined,
        perform: () => {
          // Re-set the action target so deep-linked sub-page navigation
          // (e.g. via fuzzy-search to a per-app entry) still has it.
          runtime.store.set(workspaceActionsTargetAtom, target.objectId);
        },
      });

      const preferred = getPreferredApp();
      for (const item of openWithItems) {
        out.push({
          id: `workspaces.open_in.${target.objectId}.${item.app}`,
          title: `Open in ${item.label}`,
          keywords: ["open", item.label.toLowerCase(), item.app],
          group: "workspaces",
          // Use the real app PNG so the palette matches the repo-path
          // dropdown's iconography (Finder, Cursor, VS Code, ...).
          icon: item.IconComponent,
          onPage: "workspace.open_in",
          // Surface the user's preferred app at the top of the sub-page.
          primary: preferred === item.app,
          disabled: !canOpenInOS,
          disabledReason: !canOpenInOS ? openInDisabledReason : undefined,
          perform: () => actionRuntime.openInApp(target, item.app),
        });
      }
    }

    return out;
  },
});
