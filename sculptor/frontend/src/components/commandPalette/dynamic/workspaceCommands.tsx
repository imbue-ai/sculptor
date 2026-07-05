import { useAtomValue } from "jotai";
import { ArrowUpRight } from "lucide-react";
import { type ReactElement, useMemo } from "react";

import { tasksArrayAtom } from "../../../common/state/atoms/tasks.ts";
import { workspacesArrayAtom } from "../../../common/state/atoms/workspaces.ts";
import { computeWorkspaceDotStatus } from "../../../common/utils/statusDot.ts";
import { WorkspaceStatusDots } from "../../statusDot";
import type { Command, CommandIcon, DynamicProvider } from "../types/commandPalette.ts";
import type { CommandRuntime } from "../utils/runtime.ts";

const workspaceName = (description: string | undefined): string => (description ?? "").trim() || "Untitled";

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
      for (const ws of workspaces) {
        const name = workspaceName(ws.description);
        const isCurrent = ctx.activeWorkspaceId === ws.objectId;
        out.push({
          id: `workspaces.page.${ws.objectId}`,
          title: name,
          subtitle: isCurrent ? "Current workspace" : undefined,
          keywords: ["workspace", "switch", "go to", "open", name.toLowerCase()],
          group: "workspaces",
          icon: getStatusIcon(ws.objectId),
          onPage: "workspaces.switch",
          disabled: isCurrent,
          disabledReason: isCurrent ? "Already on this workspace" : undefined,
          perform: () => runtime.navigate.toWorkspace(ws.objectId),
        });
      }

      return out;
    },
  };
};
