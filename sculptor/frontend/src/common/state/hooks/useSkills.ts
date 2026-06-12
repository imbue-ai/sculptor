import { useMemo } from "react";

import { BUILTIN_SKILLS } from "~/common/builtinSkills";
import { useWorkspacePageParams } from "~/common/NavigateUtils";

import type { SkillEntry } from "./useWorkspaceSkills";
import { useWorkspaceSkills } from "./useWorkspaceSkills";

export type { SkillEntry } from "./useWorkspaceSkills";

type UseSkillsResult = {
  skills: ReadonlyArray<SkillEntry>;
  isLoading: boolean;
  error: string | null;
};

/**
 * SkillsPanel-facing thin wrapper around `useWorkspaceSkills`. Adds the static
 * `BUILTIN_SKILLS` to the API results and sorts the merged list. While the
 * API fetch is in flight the merged list is empty (not just "API-only") to
 * match the prior behavior where the panel showed nothing during loads.
 */
export const useSkills = (): UseSkillsResult => {
  const { workspaceID } = useWorkspacePageParams();
  const { data: apiSkills, isPending, isError } = useWorkspaceSkills(workspaceID ?? null);

  const skills = useMemo<ReadonlyArray<SkillEntry>>(() => {
    if (apiSkills === undefined) return [];
    const builtins: Array<SkillEntry> = BUILTIN_SKILLS.map((s) => ({
      name: s.name,
      description: s.description,
      type: "builtin",
      filePath: null,
    }));
    return [...apiSkills, ...builtins].sort((a, b) => a.name.localeCompare(b.name));
  }, [apiSkills]);

  return {
    skills,
    isLoading: isPending,
    error: isError ? "Failed to load skills" : null,
  };
};
