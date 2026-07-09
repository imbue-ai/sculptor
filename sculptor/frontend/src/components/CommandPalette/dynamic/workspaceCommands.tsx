import { useAtomValue } from "jotai";
import { ArrowUpRight } from "lucide-react";
import { type ReactElement, useMemo } from "react";

import type { CodingAgentTaskView, Workspace } from "../../../api";
import { projectsArrayAtom } from "../../../common/state/atoms/projects.ts";
import { tasksArrayAtom } from "../../../common/state/atoms/tasks.ts";
import { workspacesArrayAtom } from "../../../common/state/atoms/workspaces.ts";
import { WorkspaceStatusDots } from "../../statusDot";
import { computeWorkspaceDotStatus, getWorkspaceAttentionRank } from "../../statusDot/statusUtils.ts";
import type { CommandRuntime } from "../runtime.ts";
import type { Command, CommandIcon, DynamicProvider } from "../types.ts";

const workspaceName = (description: string | undefined): string => (description ?? "").trim() || "Untitled";

/**
 * Millisecond timestamp of a workspace's most recent activity, used as the
 * recency tiebreak within an attention tier. There is no workspace-level
 * "last activity" field, so we take the newest task `updatedAt` and fall back
 * to the workspace's own `createdAt` for task-less workspaces. Unparseable /
 * missing timestamps collapse to 0 (sorts last within the tier).
 */
const latestActivityMs = (tasks: ReadonlyArray<CodingAgentTaskView>, ws: Workspace): number => {
  let best = ws.createdAt ? Date.parse(ws.createdAt) : 0;
  if (Number.isNaN(best)) best = 0;
  for (const task of tasks) {
    // Skip deleted tasks so the recency tiebreak counts the same tasks the
    // attention rank does (getWorkspaceAttentionRank filters them out too).
    if (task.isDeleted) continue;
    const ts = Date.parse(task.updatedAt);
    if (!Number.isNaN(ts) && ts > best) best = ts;
  }
  return best;
};

/**
 * Surfaces every open workspace in the palette so the user can jump to any
 * of them with Cmd+K. Emits two kinds of commands:
 *
 *   - `workspaces.switch` (page opener) — pushes the `workspaces.switch`
 *     sub-page when 2+ workspaces are present.
 *   - `workspaces.page.<id>` (page-scoped) — entries shown on the
 *     `workspaces.switch` sub-page. Also revealed at the root via fuzzy
 *     search (ranked below top-level matches).
 *
 * Each per-workspace row is iconed with the same status dot the tab
 * strip uses (`WorkspaceStatusDots`) so the user can see at a glance
 * whether each workspace has an unread reply, is running, errored, etc.
 * The dot component is wrapped in a per-id memoized factory so cmdk
 * sees stable component identities across produce() calls — without
 * the cache, every keystroke would mount a fresh icon component for
 * every visible row.
 */
export const buildWorkspaceProvider = (runtime: CommandRuntime): DynamicProvider => {
  const iconCache = new Map<string, CommandIcon>();
  const getStatusIcon = (workspaceId: string): CommandIcon => {
    const cached = iconCache.get(workspaceId);
    if (cached) return cached;
    const Icon = (): ReactElement => {
      const tasks = useAtomValue(tasksArrayAtom);
      const status = useMemo(
        () => computeWorkspaceDotStatus((tasks ?? []).filter((t) => t.workspaceId === workspaceId)),
        [tasks],
      );
      return <WorkspaceStatusDots status={status} />;
    };
    iconCache.set(workspaceId, Icon);
    return Icon;
  };

  return {
    id: "dynamic.workspaces",
    produce: (ctx): Array<Command> => {
      const workspaces = runtime.store.get(workspacesArrayAtom) ?? [];
      if (workspaces.length === 0) return [];

      const tasks = runtime.store.get(tasksArrayAtom) ?? [];
      const projects = runtime.store.get(projectsArrayAtom) ?? [];
      const projectNameById = new Map<string, string>();
      for (const project of projects) projectNameById.set(project.objectId, project.name);

      // The project the user is currently in, or null. Cmd+K can be opened from
      // settings / home where there is no active workspace, so this is often
      // null — every downstream use guards against that.
      const currentProjectId = workspaces.find((ws) => ws.objectId === ctx.activeWorkspaceId)?.projectId ?? null;

      // Cross-project badges only earn their keep when the list actually spans
      // more than one project — otherwise every row carries a redundant tag.
      const hasMultipleProjects = new Set(workspaces.map((ws) => ws.projectId)).size > 1;

      // Attention-first ordering, most-recent activity as the in-tier
      // tiebreak. We sort here and emit the result through each row's `order`
      // field so groupCommands honours it on the empty-query switcher page;
      // once the user types, cmdk re-ranks by fuzzy score as usual.
      const ordered = workspaces
        .map((ws) => {
          const wsTasks = tasks.filter((task) => task.workspaceId === ws.objectId);
          return { ws, rank: getWorkspaceAttentionRank(wsTasks), recencyMs: latestActivityMs(wsTasks, ws) };
        })
        .sort((a, b) => {
          if (a.rank !== b.rank) return a.rank - b.rank;
          if (a.recencyMs !== b.recencyMs) return b.recencyMs - a.recencyMs; // newer first
          return workspaceName(a.ws.description).localeCompare(workspaceName(b.ws.description));
        });

      const out: Array<Command> = [];

      // Page-opener stays visible regardless of workspace count so the
      // command shape is consistent with every other palette row (other
      // commands stay visible+disabled when they don't apply rather
      // than disappearing). With 1 workspace the sub-page shows just
      // the disabled current-workspace row — informative dead-end, not
      // a confusing one.
      out.push({
        id: "workspaces.switch",
        title: "Go to workspace...",
        subtitle: workspaces.length === 1 ? "1 workspace" : `${workspaces.length} workspaces`,
        keywords: ["change", "switch", "open", "jump"],
        // Sits in the Navigation group (above the direct-nav rows)
        // — opening a different workspace is the most common nav
        // operation, so it leads. Trailing "..." follows the
        // palette-wide convention for picker entries.
        group: "navigation",
        // ArrowUpRight is the shared visual signature for "Go to ..."
        // page-openers (mirrors agents.switch) — makes the navigation
        // group easy to spot at a glance regardless of the entity.
        icon: ArrowUpRight,
        pageId: "workspaces.switch",
        primary: true,
        // Lowest order in the Navigation group → first row.
        order: 5,
        // Top-level shortcut so the user can jump to the switcher
        // straight from anywhere — palette opens directly to the
        // workspaces.switch sub-page when this fires.
        shortcut: "open_workspace",
        perform: () => {
          // Page push handled by the runner.
        },
      });

      // Page-scoped entries — clean list when the user is on the
      // `workspaces.switch` sub-page. The current workspace appears too,
      // labelled and disabled, so the user gets a "you are here" marker
      // without firing an unintended self-navigation (which previously
      // showed a spinner while the router tried to navigate to the page
      // it was already on).
      ordered.forEach(({ ws }, index) => {
        const name = workspaceName(ws.description);
        const isCurrent = ctx.activeWorkspaceId === ws.objectId;
        const projectName = projectNameById.get(ws.projectId);
        // Tag rows that belong to a different project so a mixed list is
        // legible. Gated on the list spanning multiple projects; when anchored
        // to a current project, only the rows that differ are tagged (the
        // current project is the implicit "home", so tagging it would be
        // noise). With no current project (settings / home), every row is
        // tagged since there is nothing to contrast against.
        const shouldShowBadge =
          hasMultipleProjects &&
          projectName !== undefined &&
          (currentProjectId === null || ws.projectId !== currentProjectId);
        out.push({
          id: `workspaces.page.${ws.objectId}`,
          title: name,
          subtitle: isCurrent ? "Current workspace" : undefined,
          keywords: [
            "workspace",
            "switch",
            "go to",
            "open",
            name.toLowerCase(),
            // Let the user filter the switcher by project name too.
            ...(projectName ? [projectName.toLowerCase()] : []),
          ],
          group: "workspaces",
          icon: getStatusIcon(ws.objectId),
          trailingBadge: shouldShowBadge ? projectName : undefined,
          // Sequential rank from the attention/recency sort above; keeps the
          // empty-query switcher list in the computed order.
          order: index,
          onPage: "workspaces.switch",
          disabled: isCurrent,
          disabledReason: isCurrent ? "Already on this workspace" : undefined,
          perform: () => runtime.navigate.toWorkspace(ws.objectId),
        });
      });

      return out;
    },
  };
};
