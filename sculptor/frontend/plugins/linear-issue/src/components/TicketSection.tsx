import { Box, Flex, IconButton, Text } from "@radix-ui/themes";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import type { ReactElement } from "react";

import type { PanelTicket } from "../linear/sources.ts";
import { IssueDetails } from "./IssueDetails.tsx";
import { SourceBadge } from "./SourceBadge.tsx";
import { StateDot } from "./StateDot.tsx";

/**
 * A collapsible issue: a header (id, state, title, source badges) that toggles
 * the details. Open/closed is controlled by the panel, which derives the
 * default and persists user toggles; pinned tickets get an unpin control.
 */
export const TicketSection = ({
  ticket,
  isOpen,
  onToggle,
  subIssuesOpen,
  onToggleSubIssues,
  onUnpin,
}: {
  ticket: PanelTicket;
  isOpen: boolean;
  onToggle: () => void;
  subIssuesOpen: boolean;
  onToggleSubIssues: () => void;
  onUnpin: (identifier: string) => void;
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
