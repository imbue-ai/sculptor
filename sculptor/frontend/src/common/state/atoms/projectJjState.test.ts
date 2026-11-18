import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { ProjectJjState } from "~/api";
import { JjColocationState } from "~/api";
import { projectJjStateAtomFamily, updateProjectJjStatesAtom } from "~/common/state/atoms/projectJjState";

const makeProjectJjState = (projectId: string, overrides: Partial<ProjectJjState> = {}): ProjectJjState => ({
  projectId,
  colocation: JjColocationState.ABSENT,
  colocationError: null,
  createsJjWorkspaces: false,
  ...overrides,
});

describe("updateProjectJjStatesAtom", () => {
  it("has no state for a project the stream has not described", () => {
    const store = createStore();

    expect(store.get(projectJjStateAtomFamily("proj-a"))).toBeNull();
  });

  it("replaces a project's state with the frame's copy", () => {
    const store = createStore();
    store.set(updateProjectJjStatesAtom, { "proj-a": makeProjectJjState("proj-a") });
    const colocated = makeProjectJjState("proj-a", {
      colocation: JjColocationState.COLOCATED,
      createsJjWorkspaces: true,
    });

    store.set(updateProjectJjStatesAtom, { "proj-a": colocated });

    expect(store.get(projectJjStateAtomFamily("proj-a"))).toEqual(colocated);
  });

  it("keeps the state of a project a later frame does not mention", () => {
    const store = createStore();
    const stateA = makeProjectJjState("proj-a");
    store.set(updateProjectJjStatesAtom, { "proj-a": stateA });

    store.set(updateProjectJjStatesAtom, { "proj-b": makeProjectJjState("proj-b") });

    expect(store.get(projectJjStateAtomFamily("proj-a"))).toEqual(stateA);
  });
});
