import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { Project } from "~/api";
import { projectAtomFamily, projectsArrayAtom, updateProjectsAtom } from "~/common/state/atoms/projects";

const makeProject = (objectId: string, overrides: Partial<Project> = {}): Project => ({
  objectId,
  organizationReference: "org-1",
  name: objectId,
  userGitRepoUrl: `file:///home/dev/code/${objectId}`,
  ...overrides,
});

describe("updateProjectsAtom", () => {
  it("adds new projects after the ones already known", () => {
    const store = createStore();
    store.set(updateProjectsAtom, [makeProject("a")]);
    store.set(updateProjectsAtom, [makeProject("b")]);

    expect(store.get(projectsArrayAtom).map((p) => p.objectId)).toEqual(["a", "b"]);
  });

  it("replaces a known project with the frame's copy", () => {
    const store = createStore();
    store.set(updateProjectsAtom, [makeProject("a", { name: "old" })]);
    store.set(updateProjectsAtom, [makeProject("a", { name: "new" })]);

    expect(store.get(projectsArrayAtom).map((p) => p.name)).toEqual(["new"]);
  });

  it("removes a project the frame marks deleted", () => {
    const store = createStore();
    store.set(updateProjectsAtom, [makeProject("a"), makeProject("b")]);

    store.set(updateProjectsAtom, [makeProject("a", { isDeleted: true })]);

    expect(store.get(projectsArrayAtom).map((p) => p.objectId)).toEqual(["b"]);
    expect(store.get(projectAtomFamily("a"))).toBeNull();
  });

  it("never adds a project that arrives already deleted", () => {
    const store = createStore();
    store.set(updateProjectsAtom, [makeProject("a"), makeProject("gone", { isDeleted: true })]);

    expect(store.get(projectsArrayAtom).map((p) => p.objectId)).toEqual(["a"]);
    expect(store.get(projectAtomFamily("gone"))).toBeNull();
  });
});
