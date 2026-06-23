import { Badge, Box, Button, Flex, Text } from "@radix-ui/themes";
import { Markdown, openExternal } from "@sculptor/plugin-sdk";
import { ExternalLink, GitPullRequest } from "lucide-react";
import type { ReactElement } from "react";

import { isPullRequestAttachment, type LinearIssue, prLabel } from "../linear/client.ts";
import { TicketBadge } from "./TicketBadge.tsx";

// How many sub-issues to render before collapsing the rest into "+N more".
const MAX_SUBISSUES_SHOWN = 10;

/** The expanded body of a ticket: metadata, markdown description, and links out. */
export const IssueDetails = ({ issue }: { issue: LinearIssue }): ReactElement => {
  const prLinks = issue.attachments.filter(isPullRequestAttachment);
  const shownChildren = issue.children.slice(0, MAX_SUBISSUES_SHOWN);
  const hiddenChildCount = issue.children.length - shownChildren.length;
  return (
    <Flex direction="column" gap="3" pt="2">
      <Flex align="center" gap="2" wrap="wrap">
        {issue.priorityLabel && issue.priorityLabel !== "No priority" && (
          <Badge size="1" color="gray" variant="soft">
            {issue.priorityLabel}
          </Badge>
        )}
        {issue.assignee && (
          <Text size="1" color="gray">
            Assigned to {issue.assignee.displayName}
          </Text>
        )}
      </Flex>

      {issue.description && (
        <Box>
          <Markdown content={issue.description} />
        </Box>
      )}

      {issue.children.length > 0 && (
        <Flex direction="column" gap="2">
          <Text size="1" color="gray" weight="medium">
            Sub-issues
          </Text>
          <Flex gap="2" wrap="wrap" align="center">
            {shownChildren.map((child) => (
              <TicketBadge
                key={child.identifier}
                identifier={child.identifier}
                title={child.title}
                url={child.url}
                state={child.state}
              />
            ))}
            {hiddenChildCount > 0 && (
              // The parent's Linear page lists every sub-issue, so send the
              // overflow there rather than truncating silently.
              <Button size="1" variant="ghost" color="gray" onClick={() => openExternal(issue.url)}>
                +{hiddenChildCount} more
              </Button>
            )}
          </Flex>
        </Flex>
      )}

      <Flex gap="2" wrap="wrap">
        <Button size="1" variant="soft" onClick={() => openExternal(issue.url)}>
          <ExternalLink size={14} />
          Open in Linear
        </Button>
        {prLinks.map((attachment) => (
          <Button key={attachment.url} size="1" variant="soft" color="gray" onClick={() => openExternal(attachment.url)}>
            <GitPullRequest size={14} />
            {prLabel(attachment.url)}
          </Button>
        ))}
      </Flex>
    </Flex>
  );
};
