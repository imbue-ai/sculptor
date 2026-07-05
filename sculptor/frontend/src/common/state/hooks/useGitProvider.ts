import type { ProjectID } from "../ids.ts";
import { useRepoInfo } from "./useRepoInfo.ts";

export type GitProvider = "github" | null;

export const useGitProvider = (projectId: ProjectID): GitProvider => {
  const { repoInfo } = useRepoInfo(projectId);
  if (!projectId) return null;
  if (repoInfo?.isGithubOrigin) return "github";
  return null;
};
