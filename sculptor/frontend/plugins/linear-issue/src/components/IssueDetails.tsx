import { Badge, Box, Button, Flex, Text } from "@radix-ui/themes";
import { Markdown, openExternal } from "@sculptor/plugin-sdk";
import { ExternalLink, GitPullRequest } from "lucide-react";
import type { ReactElement } from "react";

import { isPullRequestAttachment, type LinearIssue } from "../linear/client.ts";

// "https://github.com/owner/repo/pull/74" -> "#74"; GitLab merge requests -> "!74".
const prLabel = (url: string): string => {
  const match = url.match(/\/(?:pull|merge_requests)\/(\d+)/);
  if (!match) return "PR";
  return `${url.includes("/merge_requests/") ? "!" : "#"}${match[1]}`;
};

/** The expanded body of a ticket: metadata, markdown description, and links out. */
export const IssueDetails = ({ issue }: { issue: LinearIssue }): ReactElement => {
  const prLinks = issue.attachments.filter(isPullRequestAttachment);
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
