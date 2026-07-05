import { useQuery } from "@tanstack/react-query";

import { getSkills } from "../../../api";
import type { BackendQueryKeyResult, BackendQueryResult } from "../../queryClient.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";
import type { SkillType } from "../../utils/skillBadge";

/**
 * A skill entry as exposed to consumers. The hook never produces `type:
 * "builtin"` entries — those come from the static `BUILTIN_SKILLS` list and
 * are merged in by the caller. The shared union is kept here so callers don't
 * need to widen the type when concatenating with built-ins.
 */
export type SkillEntry = {
  name: string;
  description: string;
  type: SkillType;
  filePath: string | null;
};

// `diffUpdatedAt` covers the common refresh case (skill changes that ride
// along with git activity), but two things slip past it:
//
//   1. Out-of-band on-disk edits (e.g. the user opens `~/.claude/skills/foo.md`
//      in another editor) never bump `diffUpdatedAt`.
//   2. While the workspace is still initializing, `GET /api/v1/skills` silently
//      falls back to the project's local repo, so an early fetch caches the
//      *wrong* skill set under this workspace's key (see app.py:1548). The
//      `diffUpdatedAt` cascade does eventually invalidate, but the popover
//      doesn't refetch while open (tracked in SCU-1273), so a brief stale
//      window can leak through.
//
// Keep staleness tight enough that the second case clears in a couple of
// seconds. Within-session dedup (panel + 4 editors all mounting at once)
// still works fine — those calls happen within the same animation frame and
// share the in-flight fetch regardless of `staleTime`.
const WORKSPACE_SKILLS_STALE_TIME_MS = 2_000;

const workspaceSkillsQueryKey = (workspaceId: string | null): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "git", "skills"] as const,
  isValid: workspaceId !== null,
});

const fetchWorkspaceSkills = async (workspaceId: string, signal: AbortSignal): Promise<ReadonlyArray<SkillEntry>> => {
  const { data } = await getSkills({
    query: { workspace_id: workspaceId },
    meta: { signal, skipWsAck: true },
  });
  return (data ?? []).map((skill) => ({
    name: skill.name,
    description: skill.description,
    type: skill.source === "plugin" ? "sculptor" : "custom",
    filePath: skill.filePath ?? null,
  }));
};

/**
 * Subscribe to the workspace's discovered skills. Refreshes are driven by the
 * unified WebSocket stream — `updateWorkspacesAtom` calls
 * `invalidateWorkspaceGitQueries` when the workspace's `diffUpdatedAt` changes,
 * which sweeps every cache under `["sculptor", "workspace", id, "git"]` including this
 * one. Skill files (`CLAUDE.md`, `.claude/skills/*`) typically move with git
 * activity; pure on-disk edits without any git change refresh on the next
 * mount.
 */
export const useWorkspaceSkills = (
  workspaceId: string | null,
): BackendQueryResult<ReadonlyArray<SkillEntry> | undefined> => {
  const { key, isValid } = workspaceSkillsQueryKey(workspaceId);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchWorkspaceSkills(workspaceId!, signal),
    enabled: isValid,
    staleTime: WORKSPACE_SKILLS_STALE_TIME_MS,
    // Skills failures are usually a real backend problem (e.g. plugin loader
    // throwing) rather than a transient blip — surface the error promptly
    // instead of masking it behind a retry delay.
    retry: false,
  });

  return {
    data: query.data,
    isPending: query.isPending,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
};

/**
 * Get fresh workspace skills, returning the cached value if it's within the
 * stale window and refetching otherwise. Used by non-React callers (the tiptap
 * `/`-suggestion plugin) so every editor instance shares a single fetch with
 * the panel. Goes through `fetchQuery` rather than `ensureQueryData` because
 * the latter returns *any* cached data regardless of age — it only consults
 * `staleTime` when paired with `revalidateIfStale`, and even then only as a
 * fire-and-forget background hint. `fetchQuery` actually awaits the refetch
 * when stale, which is what `/`-press freshness needs.
 */
export const fetchFreshWorkspaceSkills = async (workspaceId: string | null): Promise<ReadonlyArray<SkillEntry>> => {
  const { key, isValid } = workspaceSkillsQueryKey(workspaceId);
  if (!isValid) return [];
  return await queryClient.fetchQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchWorkspaceSkills(workspaceId!, signal),
    staleTime: WORKSPACE_SKILLS_STALE_TIME_MS,
  });
};
