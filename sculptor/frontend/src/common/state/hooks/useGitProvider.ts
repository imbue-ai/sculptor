import type { GitProvider } from "~/pages/workspace/components/PrButton.tsx";

import type { ProjectID } from "../../Types";
import { useRepoInfo } from "./useRepoInfo.ts";

export const useGitProvider = (projectId: ProjectID): GitProvider => {
  const { repoInfo } = useRepoInfo(projectId);
  if (!projectId) return null;
  if (repoInfo?.isGitlabOrigin) return "gitlab";
  if (repoInfo?.isGithubOrigin) return "github";
  return null;
};
