import { useAtomValue } from "jotai";

import type { Project } from "../../../api";
import { projectAtomFamily, projectsArrayAtom } from "../atoms/projects";

export const useProject = (projectId: string): Project | null => {
  return useAtomValue(projectAtomFamily(projectId));
};

export const useProjects = (): ReadonlyArray<Project> => {
  return useAtomValue(projectsArrayAtom);
};
