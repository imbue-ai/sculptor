import { Box, Button, Flex, IconButton, Spinner, Text } from "@radix-ui/themes";
import { PanelHeader, useCurrentWorkspace, usePluginSetting } from "@sculptor/plugin-sdk";
import { RefreshCw } from "lucide-react";
import type { ReactElement } from "react";

import { useExpandedIds } from "../linear/useExpandedIds.ts";
import { useLinearTickets } from "../linear/useLinearTickets.ts";
import { usePinnedIds } from "../linear/usePinnedIds.ts";
import { EmptyState } from "./EmptyState.tsx";
import { QuickSearch } from "./QuickSearch.tsx";
import { TicketSection } from "./TicketSection.tsx";

/**
 * The Linear panel. Shows the workspace's tickets as collapsible sections — the
 * branch's issue (primary, accented), the issues its PR links, and any the user
 * pins via quick-search — each tagged with where it came from.
 */
export const LinearPanel = (): ReactElement => {
  const branch = useCurrentWorkspace((workspace) => workspace?.branch ?? null);
  const workspaceId = useCurrentWorkspace((workspace) => workspace?.id ?? null);
  const [apiKey] = usePluginSetting("apiKey");
  const { pinnedIds, pin, unpin } = usePinnedIds(workspaceId);
  const { overrides, setExpanded } = useExpandedIds(workspaceId);
  // A separate map for each ticket's sub-issue disclosure, keyed by the same
  // ticket identifier but namespaced so it can't collide with the section map.
  const { overrides: subOverrides, setExpanded: setSubExpanded } = useExpandedIds(workspaceId, "subissues");
  const { tickets, isFetching, isError, error, refetch } = useLinearTickets({ apiKey, branch, pinnedIds });

  const refreshAction = apiKey ? (
    <IconButton size="1" variant="ghost" color="gray" onClick={() => refetch()} disabled={isFetching} title="Refresh">
      <RefreshCw size={14} />
    </IconButton>
  ) : undefined;

  const renderTickets = (): ReactElement => {
    if (tickets.length > 0) {
      return (
        <Flex direction="column" gap="2">
          {tickets.map((ticket) => {
            const id = ticket.issue.identifier;
            // A user toggle wins; otherwise open the primary, and open a lone
            // ticket of any source so a single result is never left collapsed.
            const defaultOpen = ticket.isPrimary || tickets.length === 1;
            const isOpen = overrides[id] ?? defaultOpen;
            // Sub-issues stay collapsed until asked for, keeping the body compact.
            const subIssuesDefaultOpen = false;
            const subIssuesOpen = subOverrides[id] ?? subIssuesDefaultOpen;
            return (
              <TicketSection
                key={id}
                ticket={ticket}
                isOpen={isOpen}
                onToggle={() => setExpanded(id, !isOpen, defaultOpen)}
                subIssuesOpen={subIssuesOpen}
                onToggleSubIssues={() => setSubExpanded(id, !subIssuesOpen, subIssuesDefaultOpen)}
                onUnpin={unpin}
              />
            );
          })}
        </Flex>
      );
    }
    if (branch === null && pinnedIds.length === 0) {
      return <EmptyState message="Waiting for the workspace branch…" />;
    }
    if (isFetching) {
      return (
        <Flex align="center" justify="center" gap="2" p="5">
          <Spinner size="1" />
          <Text size="2" color="gray">
            Loading…
          </Text>
        </Flex>
      );
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
    return (
      <EmptyState
        message={
          branch ? `No Linear ticket linked to "${branch}". Search above to add one.` : "Search above to add a ticket."
        }
      />
    );
  };

  return (
    <Flex direction="column" height="100%">
      <PanelHeader title="Linear" actions={refreshAction} />
      {!apiKey ? (
        <EmptyState message="Add your Linear API key in the plugin settings to link branches to issues." />
      ) : (
        <Flex direction="column" style={{ flexGrow: 1, minHeight: 0 }}>
          {/* Search sits outside the scroll area so its dropdown isn't clipped. */}
          <Box p="2">
            <QuickSearch apiKey={apiKey} pinnedIds={pinnedIds} onPin={pin} />
          </Box>
          <Box px="2" pb="2" style={{ overflowY: "auto", flexGrow: 1 }}>
            {renderTickets()}
          </Box>
        </Flex>
      )}
    </Flex>
  );
};
