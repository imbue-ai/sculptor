import { useQuery } from "@tanstack/react-query";

import { getSkills } from "../../../api";
import type { BackendQueryKeyResult, BackendQueryResult } from "../queryClient.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "../queryClient.ts";
import type { SkillEntry } from "./useWorkspaceSkills";

const projectSkillsQueryKey = (projectId: string | null): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "project", projectId, "skills"] as const,
  isValid: projectId !== null,
});

const fetchProjectSkills = async (projectId: string, signal: AbortSignal): Promise<ReadonlyArray<SkillEntry>> => {
  const { data } = await getSkills({
    query: { project_id: projectId },
    meta: { signal, skipWsAck: true },
  });
  return (data ?? []).map((skill) => ({
    name: skill.name,
    description: skill.description,
    type: skill.source === "plugin" ? "sculptor" : "custom",
    filePath: skill.filePath ?? null,
  }));
};

// Project-scoped skill fetches go through the project's local repo and have
// no per-workspace WebSocket trigger to invalidate them. The shared
// `queryClient` defaults to `staleTime: Infinity` because workspace-scoped
// queries refresh via explicit invalidation; the project hook overrides
// `staleTime` to a short window so the next `/` press or remount after the
// window picks up on-disk edits (the user adds a skill file and types `/`
// again), while still deduping rapid `/` re-presses, the eager prefetch, and
// concurrent editor mounts within the window.
const PROJECT_SKILLS_STALE_TIME_MS = 10_000;

/**
 * Subscribe to the discovered skills for a project (Add Workspace page,
 * project-level chat input). Used when no workspace exists yet — the backend
 * inspects the project's local repo.
 */
export const useProjectSkills = (
  projectId: string | null,
): BackendQueryResult<ReadonlyArray<SkillEntry> | undefined> => {
  const { key, isValid } = projectSkillsQueryKey(projectId);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchProjectSkills(projectId!, signal),
    enabled: isValid,
    staleTime: PROJECT_SKILLS_STALE_TIME_MS,
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
 * Get fresh project skills, returning the cached value if it's within the
 * stale window and refetching otherwise. See `fetchFreshWorkspaceSkills` for
 * why this uses `fetchQuery` rather than `ensureQueryData`.
 */
export const fetchFreshProjectSkills = async (projectId: string | null): Promise<ReadonlyArray<SkillEntry>> => {
  const { key, isValid } = projectSkillsQueryKey(projectId);
  if (!isValid) return [];
  return await queryClient.fetchQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchProjectSkills(projectId!, signal),
    staleTime: PROJECT_SKILLS_STALE_TIME_MS,
  });
};
