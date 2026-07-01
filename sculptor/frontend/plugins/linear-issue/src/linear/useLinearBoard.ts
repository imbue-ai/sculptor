import { usePluginSettings, useWorkspaces, type WorkspaceView } from "@sculptor/plugin-sdk";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { PLUGIN_ID } from "../constants.ts";
import { type BoardGroup, buildBoard } from "./board.ts";
import { fetchAssignedIssues } from "./client.ts";
import { parseTicket } from "./ticket.ts";
import { ticketAssignmentKey } from "./useTicketAssignment.ts";

// Same caching posture as the panel's ticket queries: cached on the host's
// shared QueryClient (so the board survives view switches), with an explicit
// staleTime because the host default is Infinity. The API key is deliberately
// never part of the key (keys are visible in cache inspection); the settings
// component invalidates this plugin's namespace when the key changes.
const STALE_TIME = 60_000;
const GC_TIME = 30 * 60_000;

// Most-recently-updated assigned issues to pull. Generous enough to cover all
// active work plus a tail of recent completions; buildBoard caps the terminal
// groups so the surplus completed tickets don't dominate.
const ASSIGNED_LIMIT = 50;

export type LinearBoardData = {
  groups: ReadonlyArray<BoardGroup<WorkspaceView>>;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
};

/**
 * The board's data: the current user's assigned issues (one cached query),
 * grouped by workflow state and joined against every workspace so each ticket
 * knows whether a workspace is already working it.
 */
export const useLinearBoard = (apiKey: string): LinearBoardData => {
  const query = useQuery({
    queryKey: [PLUGIN_ID, "assigned"],
    queryFn: ({ signal }) => fetchAssignedIssues({ apiKey, limit: ASSIGNED_LIMIT, signal }),
    enabled: Boolean(apiKey),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });

  const workspaces = useWorkspaces();

  // Each workspace's explicit ticket assignment (what the panel/banner sets),
  // read reactively under the same per-workspace keys the panel writes — so a
  // workspace the user has assigned to a ticket whose id isn't in its branch
  // still shows up under that ticket, with no per-workspace re-resolution.
  const assignmentKeys = useMemo(
    () => (workspaces ?? []).map((workspace) => ticketAssignmentKey(workspace.id)),
    [workspaces],
  );
  const assignments = usePluginSettings(assignmentKeys);
  const linkedWorkspaces = useMemo(
    () =>
      (workspaces ?? []).map((workspace) => ({
        ...workspace,
        assignedTicketId: parseTicket(assignments.get(ticketAssignmentKey(workspace.id)) ?? null)?.identifier ?? null,
      })),
    [workspaces, assignments],
  );

  const groups = useMemo(() => buildBoard(query.data ?? [], linkedWorkspaces), [query.data, linkedWorkspaces]);

  return {
    groups,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: (): void => void query.refetch(),
  };
};
