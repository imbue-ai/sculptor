import { describe, expect, it } from "vitest";

import type { JjColocationState, ProjectJjState } from "~/api";

import { getColocationSwitchState, getUseJjSwitchState } from "./repoJjControlState.ts";

const jjState = (colocation: JjColocationState, colocationError: string | null = null): ProjectJjState => ({
  projectId: "prj-1",
  colocation,
  colocationError,
  createsJjWorkspaces: colocation === "COLOCATED",
});

describe("getColocationSwitchState", () => {
  it("is unavailable while jj is unavailable, whatever the stream says", () => {
    expect(
      getColocationSwitchState({ isJjAvailable: false, jjState: jjState("ABSENT"), isColocationRequested: false }),
    ).toEqual({ kind: "UNAVAILABLE" });
    expect(
      getColocationSwitchState({ isJjAvailable: false, jjState: jjState("ABSENT"), isColocationRequested: true }),
    ).toEqual({ kind: "UNAVAILABLE" });
  });

  it("is off for a repository the stream reads as absent", () => {
    expect(
      getColocationSwitchState({ isJjAvailable: true, jjState: jjState("ABSENT"), isColocationRequested: false }),
    ).toEqual({ kind: "OFF" });
  });

  it("is off before the stream describes the repository", () => {
    expect(getColocationSwitchState({ isJjAvailable: true, jjState: null, isColocationRequested: false })).toEqual({
      kind: "OFF",
    });
  });

  it("is initializing while the stream says a colocation is running", () => {
    expect(
      getColocationSwitchState({
        isJjAvailable: true,
        jjState: jjState("INITIALIZING"),
        isColocationRequested: false,
      }),
    ).toEqual({ kind: "INITIALIZING" });
  });

  it("is initializing once requested, before the stream says so", () => {
    expect(
      getColocationSwitchState({ isJjAvailable: true, jjState: jjState("ABSENT"), isColocationRequested: true }),
    ).toEqual({ kind: "INITIALIZING" });
    expect(
      getColocationSwitchState({
        isJjAvailable: true,
        jjState: jjState("FAILED", "boom"),
        isColocationRequested: true,
      }),
    ).toEqual({ kind: "INITIALIZING" });
  });

  it("is locked on for a colocated repository, even with a request still settling", () => {
    expect(
      getColocationSwitchState({ isJjAvailable: true, jjState: jjState("COLOCATED"), isColocationRequested: false }),
    ).toEqual({ kind: "ON_LOCKED" });
    expect(
      getColocationSwitchState({ isJjAvailable: true, jjState: jjState("COLOCATED"), isColocationRequested: true }),
    ).toEqual({ kind: "ON_LOCKED" });
  });

  it("carries the error of a failed colocation", () => {
    expect(
      getColocationSwitchState({
        isJjAvailable: true,
        jjState: jjState("FAILED", "jj git init exited 1"),
        isColocationRequested: false,
      }),
    ).toEqual({ kind: "FAILED", error: "jj git init exited 1" });
  });
});

describe("getUseJjSwitchState", () => {
  it("is unavailable while jj is unavailable, showing the stored value", () => {
    expect(
      getUseJjSwitchState({
        isJjAvailable: false,
        colocation: "ABSENT",
        storedValue: true,
        requestedValue: undefined,
      }),
    ).toEqual({ kind: "UNAVAILABLE", isChecked: true });
  });

  it("waits for the colocation when the repository is not colocated", () => {
    for (const colocation of ["ABSENT", "INITIALIZING", "FAILED", undefined] as const) {
      expect(
        getUseJjSwitchState({ isJjAvailable: true, colocation, storedValue: false, requestedValue: undefined }),
      ).toEqual({ kind: "NOT_COLOCATED", isChecked: false });
    }
  });

  it("shows the stored value of a colocated repository", () => {
    expect(
      getUseJjSwitchState({
        isJjAvailable: true,
        colocation: "COLOCATED",
        storedValue: true,
        requestedValue: undefined,
      }),
    ).toEqual({ kind: "ENABLED", isChecked: true });
  });

  it("shows the requested value while the request is pending", () => {
    expect(
      getUseJjSwitchState({ isJjAvailable: true, colocation: "COLOCATED", storedValue: true, requestedValue: false }),
    ).toEqual({ kind: "ENABLED", isChecked: false });
  });
});
