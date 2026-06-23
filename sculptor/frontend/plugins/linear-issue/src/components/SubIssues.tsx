import { Box, Button, Flex, Text } from "@radix-ui/themes";
import { openExternal } from "@sculptor/plugin-sdk";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ReactElement } from "react";

import type { LinearIssue } from "../linear/client.ts";
import { TicketBadge } from "./TicketBadge.tsx";

// How many sub-issues to render before collapsing the rest into "+N more".
const MAX_SUBISSUES_SHOWN = 10;

/**
 * A light, collapsible disclosure of an issue's sub-issues: a header that just
 * counts them, expanding to a slightly-indented list of sub-issue badges. Keeps
 * the ticket body compact until the reader asks for the nesting. Open state is
 * owned and persisted by the panel (so it survives the panel remounting);
 * renders nothing when the issue has no sub-issues.
 */
export const SubIssues = ({
  issue,
  isOpen,
  onToggle,
}: {
  issue: LinearIssue;
  isOpen: boolean;
  onToggle: () => void;
}): ReactElement | null => {
  const count = issue.children.length;
  if (count === 0) return null;
  const shown = issue.children.slice(0, MAX_SUBISSUES_SHOWN);
  const hidden = count - shown.length;
  return (
    <Flex direction="column" gap="2">
      <Flex align="center" gap="1" onClick={onToggle} style={{ cursor: "pointer", width: "fit-content" }}>
        {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Text size="1" color="gray">
          {count} sub-issue{count === 1 ? "" : "s"}
        </Text>
      </Flex>
      {isOpen && (
        // A faint left border + indent reads as nesting under the parent ticket.
        <Box pl="3" style={{ borderLeft: "1px solid var(--gray-4)", marginLeft: "var(--space-1)" }}>
          <Flex gap="2" wrap="wrap" align="center">
            {shown.map((child) => (
              <TicketBadge
                key={child.identifier}
                identifier={child.identifier}
                title={child.title}
                url={child.url}
                state={child.state}
              />
            ))}
            {hidden > 0 && (
              // The parent's Linear page lists every sub-issue, so send the
              // overflow there rather than truncating silently.
              <Button size="1" variant="ghost" color="gray" onClick={() => openExternal(issue.url)}>
                +{hidden} more
              </Button>
            )}
          </Flex>
        </Box>
      )}
    </Flex>
  );
};
