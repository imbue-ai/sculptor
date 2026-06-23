import { Button, Tooltip } from "@radix-ui/themes";
import { openExternal, useCurrentWorkspace, usePluginSetting } from "@sculptor/plugin-sdk";
import { Hash } from "lucide-react";
import type { ReactElement } from "react";

import { useShortcut } from "../linear/useShortcut.ts";
import { useShortcutTicket } from "../linear/useShortcutTicket.ts";
import { StateDot } from "./StateDot.tsx";

/**
 * The compact Linear shortcut the host places in the workspace banner, beside
 * the PR button. It tracks the same ticket as the panel: defaulting to the
 * branch's issue, but following whatever the user assigns as the shortcut from
 * the panel (the shared per-workspace `shortcut` setting). Clicking opens the
 * issue in Linear.
 *
 * It renders nothing until there is something to link to (no API key, or no
 * branch/assigned ticket resolved yet) rather than show an empty chip — the
 * banner row stays clean for workspaces with no linked Linear issue.
 */
export const WorkspaceShortcutWidget = (): ReactElement | null => {
  const branch = useCurrentWorkspace((workspace) => workspace?.branch ?? null);
  const workspaceId = useCurrentWorkspace((workspace) => workspace?.id ?? null);
  const [apiKey] = usePluginSetting("apiKey");
  const { shortcutId } = useShortcut(workspaceId);
  const { issue, isDefault } = useShortcutTicket({ apiKey, branch, shortcutId });

  if (!apiKey || !issue) return null;

  const tooltip = `${issue.title}${isDefault ? "" : " · assigned shortcut"} — open in Linear`;

  return (
    <Tooltip content={tooltip}>
      <Button
        size="1"
        // Ghost (not soft) so the chip is content-height, matching the diff
        // summary and PR button beside it — Radix's soft/solid variants force a
        // taller fixed control height that would stand proud of the banner row.
        variant="ghost"
        color="gray"
        onClick={() => openExternal(issue.url)}
        data-testid="linear-workspace-shortcut"
      >
        <Hash size={12} />
        {issue.identifier}
        {issue.state && <StateDot color={issue.state.color} />}
      </Button>
    </Tooltip>
  );
};
