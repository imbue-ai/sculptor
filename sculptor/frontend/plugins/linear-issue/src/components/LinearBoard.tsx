import { Badge, Box, Button, Flex, Heading, IconButton, Spinner, Text } from "@radix-ui/themes";
import { useNavigateToWorkspace, usePluginSetting, type WorkspaceView } from "@sculptor/plugin-sdk";
import { RefreshCw } from "lucide-react";
import type { ReactElement } from "react";

import { type BoardGroup } from "../linear/board.ts";
import { useLinearBoard } from "../linear/useLinearBoard.ts";
import { BoardTicketRow } from "./BoardTicketRow.tsx";
import { EmptyState } from "./EmptyState.tsx";
import { StateIcon } from "./StateIcon.tsx";

/**
 * The Linear board home view: the current user's assigned issues, grouped by
 * workflow state, each ticket flagged with whether a Sculptor workspace is
 * already working it. Registered as a homepage view (see index.tsx), so it
 * owns the whole content area below the home switcher and reads app state
 * through the SDK rather than a single workspace context.
 */
export const LinearBoard = (): ReactElement => {
  const [apiKey] = usePluginSetting("apiKey");
  const navigateToWorkspace = useNavigateToWorkspace();
  const { groups, isFetching, isError, error, refetch } = useLinearBoard(apiKey);

  return (
    <Flex direction="column" style={{ flex: 1, minHeight: 0, background: "var(--gray-2)" }}>
      <Flex justify="center" style={{ flex: "0 0 auto", padding: "var(--space-4) var(--space-5) 0" }}>
        {/* gap="2" because the Radix IconButton applies negative hover margins. */}
        <Flex align="center" justify="between" gap="2" width="100%" style={{ maxWidth: 850 }}>
          <Heading size="3">Assigned to you</Heading>
          {apiKey ? (
            <IconButton
              size="1"
              variant="ghost"
              color="gray"
              onClick={() => refetch()}
              disabled={isFetching}
              title="Refresh"
              aria-label="Refresh assigned issues"
            >
              <RefreshCw size={14} />
            </IconButton>
          ) : null}
        </Flex>
      </Flex>

      <Box
        style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "var(--space-4) var(--space-5) var(--space-6)" }}
      >
        <Box style={{ maxWidth: 850, margin: "0 auto" }}>
          <BoardBody
            apiKey={apiKey}
            groups={groups}
            isFetching={isFetching}
            isError={isError}
            error={error}
            refetch={refetch}
            onOpenWorkspace={navigateToWorkspace}
          />
        </Box>
      </Box>
    </Flex>
  );
};

const BoardBody = ({
  apiKey,
  groups,
  isFetching,
  isError,
  error,
  refetch,
  onOpenWorkspace,
}: {
  apiKey: string;
  groups: ReadonlyArray<BoardGroup<WorkspaceView>>;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
  onOpenWorkspace: (workspaceId: string) => void;
}): ReactElement => {
  if (!apiKey) {
    return <EmptyState message="Add your Linear API key in the plugin settings to see your assigned issues." />;
  }
  if (isError) {
    return (
      <EmptyState
        message={error instanceof Error ? error.message : String(error)}
        action={
          <Button size="1" variant="soft" onClick={() => refetch()}>
            Retry
          </Button>
        }
      />
    );
  }
  // First load (no cached groups yet): a spinner. A background refetch with
  // groups already present keeps the list visible instead of flashing empty.
  if (groups.length === 0 && isFetching) {
    return (
      <Flex align="center" justify="center" gap="2" p="6">
        <Spinner size="1" />
        <Text size="2" color="gray">
          Loading your issues…
        </Text>
      </Flex>
    );
  }
  if (groups.length === 0) {
    return <EmptyState message="No issues are assigned to you right now." />;
  }
  return (
    <Flex direction="column" gap="4">
      {groups.map((group) => (
        <BoardGroupSection key={group.key} group={group} onOpenWorkspace={onOpenWorkspace} />
      ))}
    </Flex>
  );
};

const BoardGroupSection = ({
  group,
  onOpenWorkspace,
}: {
  group: BoardGroup<WorkspaceView>;
  onOpenWorkspace: (workspaceId: string) => void;
}): ReactElement => {
  const total = group.rows.length + group.hiddenCount;
  return (
    <Box>
      <Flex align="center" gap="2" mb="1" px="2">
        <StateIcon type={group.stateType} color={group.color ?? ""} size={14} />
        <Text size="2" weight="medium">
          {group.stateName}
        </Text>
        <Badge size="1" variant="soft" color="gray" radius="full">
          {total}
        </Badge>
      </Flex>
      <Box style={{ borderBottom: "1px solid var(--gray-a3)" }}>
        {group.rows.map((row) => (
          <BoardTicketRow key={row.issue.identifier} row={row} onOpenWorkspace={onOpenWorkspace} />
        ))}
      </Box>
      {group.hiddenCount > 0 ? (
        <Text size="1" color="gray" mt="1" ml="2" as="div">
          +{group.hiddenCount} more
        </Text>
      ) : null}
    </Box>
  );
};
