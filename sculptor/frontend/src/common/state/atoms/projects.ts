import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { Project } from "../../../api";

export const projectAtomFamily = atomFamily<string, PrimitiveAtom<Project | null>>(() => atom<Project | null>(null));

export const projectIdsAtom = atom<ReadonlyArray<string>>([]);

export const projectsArrayAtom = atom<ReadonlyArray<Project>>((get) => {
  const projectIds = get(projectIdsAtom);
  const allProjects = projectIds
    .map((id) => get(projectAtomFamily(id)))
    .filter((project): project is Project => project !== null);

  // Deduplicate by repo URL to handle legacy projects with different IDs for the same path
  const seenUrls = new Set<string>();
  return allProjects.filter((project) => {
    const url = project.userGitRepoUrl;
    if (!url) return true;
    if (seenUrls.has(url)) return false;
    seenUrls.add(url);
    return true;
  });
});

export const updateProjectsAtom = atom(null, (get, set, projects: ReadonlyArray<Project>) => {
  const deltaProjectIds = projects.map((project) => project.objectId);
  const currentProjectIds = get(projectIdsAtom);

  projects.forEach((project) => {
    set(projectAtomFamily(project.objectId), project);
  });

  // Merge delta IDs with existing IDs (add any new ones, keep all existing ones)
  const existingIdSet = new Set(currentProjectIds);
  const newIds = deltaProjectIds.filter((id) => !existingIdSet.has(id));

  // Only update the IDs array if there are new projects
  if (newIds.length > 0) {
    set(projectIdsAtom, [...currentProjectIds, ...newIds]);
  }
});

export const removeProjectAtom = atom(null, (get, set, projectId: string) => {
  const currentProjectIds = get(projectIdsAtom);
  if (!currentProjectIds.includes(projectId)) {
    return;
  }

  set(projectAtomFamily(projectId), null);
  set(
    projectIdsAtom,
    currentProjectIds.filter((id) => id !== projectId),
  );
});
