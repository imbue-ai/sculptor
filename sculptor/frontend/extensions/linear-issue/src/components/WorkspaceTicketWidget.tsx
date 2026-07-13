import { Tooltip } from "@radix-ui/themes";
import { openExternal, useCurrentWorkspace, useExtensionSetting } from "@sculptor/extension-sdk";
import type { CSSProperties, ReactElement } from "react";
import { useState } from "react";

import { useTicketAssignment } from "../linear/useTicketAssignment.ts";
import { useWorkspaceTicketIssue } from "../linear/useWorkspaceTicketIssue.ts";
import { StateIcon } from "./StateIcon.tsx";

// Mirrors the host PR button's chip (PrButton.module.scss): a filled gray-a3
// chip, 2px/space-2 padding, radius-2, font-size-1, with a gray-a4 hover. The
// extension compiles to a lone main.js with no CSS asset the host would load, so
// the chip is styled inline rather than with a CSS module — hence the hover is
// driven by state instead of a `:hover` rule.
const CHIP_BASE: CSSProperties = {
  alignItems: "center",
  border: "none",
  borderRadius: "var(--radius-2)",
  color: "var(--gray-12)",
  cursor: "pointer",
  display: "inline-flex",
  fontFamily: "var(--default-font-family)",
  fontSize: "var(--font-size-1)",
  gap: "var(--space-1)",
  lineHeight: "var(--line-height-1)",
  padding: "2px var(--space-2)",
  whiteSpace: "nowrap",
};

/**
 * The compact Linear ticket chip the host places in the workspace banner, beside
 * the PR button. It tracks the same ticket as the panel: defaulting to the
 * branch's issue, but following whatever ticket the user assigns to the
 * workspace from the panel (the shared per-workspace assignment setting).
 * Clicking opens the issue in Linear.
 *
 * It renders nothing until there is something to link to (no API key, or no
 * branch/assigned ticket resolved yet) rather than show an empty chip — the
 * banner row stays clean for workspaces with no linked Linear issue.
 */
export const WorkspaceTicketWidget = (): ReactElement | null => {
  const branch = useCurrentWorkspace((workspace) => workspace?.branch ?? null);
  const workspaceId = useCurrentWorkspace((workspace) => workspace?.id ?? null);
  const pullRequestUrl = useCurrentWorkspace((workspace) => workspace?.pullRequestUrl ?? null);
  const [apiKey] = useExtensionSetting("apiKey");
  const { assignedTicketId } = useTicketAssignment(workspaceId);
  const { issue, isDefault } = useWorkspaceTicketIssue({ apiKey, branch, pullRequestUrl, assignedTicketId });
  const [isHovered, setIsHovered] = useState(false);

  if (!apiKey || !issue) return null;

  // A cancelled ticket is terminal and likely stale, so mute it the way the PR
  // button mutes a merged/closed PR (gray-a2 + struck identifier) — a glance is
  // enough to spot a still-open PR pointing at an abandoned ticket.
  // Linear's terminal state type is "canceled" (one "l").
  const isCancelled = issue.state?.type === "canceled";
  const stateLabel = issue.state ? ` · ${issue.state.name}` : "";
  const tooltip = `${issue.title}${stateLabel}${isDefault ? "" : " · assigned ticket"} — open in Linear`;

  // Cancelled tickets sit one step more muted than active ones, mirroring the
  // merged/closed PR button (gray-a2 vs gray-a3).
  const idleBackground = isCancelled ? "var(--gray-a2)" : "var(--gray-a3)";
  const hoverBackground = isCancelled ? "var(--gray-a3)" : "var(--gray-a4)";

  return (
    <Tooltip content={tooltip}>
      <button
        type="button"
        style={{ ...CHIP_BASE, background: isHovered ? hoverBackground : idleBackground }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={() => openExternal(issue.url)}
        data-testid="linear-workspace-ticket"
      >
        {/* Leading glyph: the ticket's workflow state, tinted by the state
            color. StateIcon supplies a neutral fallback when the color is
            absent. */}
        <StateIcon type={issue.state?.type ?? null} color={issue.state?.color ?? ""} size={12} />
        {/* Same monospace token as the PR button's "PR #123" beside it. */}
        <span
          style={{
            fontFamily: "var(--mono-font-family)",
            color: isCancelled ? "var(--gray-11)" : undefined,
            textDecoration: isCancelled ? "line-through" : undefined,
          }}
        >
          {issue.identifier}
        </span>
      </button>
    </Tooltip>
  );
};
