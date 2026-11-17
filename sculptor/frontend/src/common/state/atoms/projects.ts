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

/** Apply the projects in a stream frame: upsert the live ones and drop the ones
 * marked deleted. Only the unified stream writes project state. */
export const updateProjectsAtom = atom(null, (get, set, projects: ReadonlyArray<Project>) => {
  const currentProjectIds = get(projectIdsAtom);
  const existingIdSet = new Set(currentProjectIds);
  const deletedIdSet = new Set(projects.filter((project) => project.isDeleted).map((project) => project.objectId));
  const liveProjects = projects.filter((project) => !project.isDeleted);

  liveProjects.forEach((project) => {
    set(projectAtomFamily(project.objectId), project);
  });
  deletedIdSet.forEach((projectId) => {
    set(projectAtomFamily(projectId), null);
  });

  const keptIds = currentProjectIds.filter((id) => !deletedIdSet.has(id));
  const newIds = liveProjects.map((project) => project.objectId).filter((id) => !existingIdSet.has(id));
  if (newIds.length > 0 || keptIds.length !== currentProjectIds.length) {
    set(projectIdsAtom, [...keptIds, ...newIds]);
  }
});
