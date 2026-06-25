import { Box, Flex, IconButton, Text } from "@radix-ui/themes";
import { Bookmark, ChevronDown, ChevronRight, X } from "lucide-react";
import type { ReactElement } from "react";

import type { PanelTicket } from "../linear/sources.ts";
import { IssueDetails } from "./IssueDetails.tsx";
import { SourceBadge } from "./SourceBadge.tsx";
import { StateDot } from "./StateDot.tsx";

/**
 * A collapsible issue: a header (id, state, title, source badges) that toggles
 * the details. Open/closed is controlled by the panel, which derives the
 * default and persists user toggles; pinned tickets get an unpin control. A
 * bookmark control assigns the ticket as the workspace shortcut shown in the
 * banner widget — filled on the ticket that is currently the shortcut.
 */
export const TicketSection = ({
  ticket,
  isOpen,
  onToggle,
  subIssuesOpen,
  onToggleSubIssues,
  onUnpin,
  isShortcut,
  onToggleShortcut,
}: {
  ticket: PanelTicket;
  isOpen: boolean;
  onToggle: () => void;
  subIssuesOpen: boolean;
  onToggleSubIssues: () => void;
  onUnpin: (identifier: string) => void;
  /** Whether this ticket is the workspace's current (effective) shortcut. */
  isShortcut: boolean;
  /** Assign this ticket as the shortcut, or clear it if it already is one. */
  onToggleShortcut: () => void;
}): ReactElement => {
  const { issue } = ticket;
  const canUnpin = ticket.sources.includes("pinned");

  return (
    <Box
      style={{
        border: "1px solid var(--gray-4)",
        borderLeft: ticket.isPrimary ? "2px solid var(--accent-9)" : "1px solid var(--gray-4)",
        borderRadius: "var(--radius-3)",
      }}
    >
      <Flex align="center" gap="2" p="2" onClick={() => onToggle()} style={{ cursor: "pointer" }}>
        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Text size="1" color="gray" style={{ fontFamily: "var(--code-font-family)", flexShrink: 0 }}>
          {issue.identifier}
        </Text>
        {issue.state && <StateDot color={issue.state.color} />}
        <Text size="2" weight={ticket.isPrimary ? "medium" : "regular"} truncate style={{ flexGrow: 1 }}>
          {issue.title}
        </Text>
        <Flex align="center" gap="2" style={{ flexShrink: 0 }}>
          {ticket.sources.map((source) => (
            <SourceBadge key={source} source={source} primary={ticket.isPrimary && source === "branch"} />
          ))}
          <IconButton
            size="1"
            variant="ghost"
            color={isShortcut ? undefined : "gray"}
            title={isShortcut ? "Clear workspace shortcut" : "Use as workspace shortcut"}
            aria-pressed={isShortcut}
            onClick={(e) => {
              e.stopPropagation();
              onToggleShortcut();
            }}
          >
            <Bookmark size={12} fill={isShortcut ? "currentColor" : "none"} />
          </IconButton>
          {canUnpin && (
            <IconButton
              size="1"
              variant="ghost"
              color="gray"
              title="Unpin"
              onClick={(e) => {
                e.stopPropagation();
                onUnpin(issue.identifier);
              }}
            >
              <X size={12} />
            </IconButton>
          )}
        </Flex>
      </Flex>
      {isOpen && (
        <Box px="2" pb="2">
          <IssueDetails issue={issue} subIssuesOpen={subIssuesOpen} onToggleSubIssues={onToggleSubIssues} />
        </Box>
      )}
    </Box>
  );
};
