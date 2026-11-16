import { describe, expect, it } from "vitest";

import { findTargetForPrBase, isPrBaseOtherThanTarget } from "./prBaseNames.ts";

describe("isPrBaseOtherThanTarget", () => {
  it("is false when the target opens pull requests into the PR's base", () => {
    expect(
      isPrBaseOtherThanTarget({ prBaseName: "main", targetRef: "origin/main", prBaseNames: { "origin/main": "main" } }),
    ).toBe(false);
  });

  it("is true when the target opens pull requests into another base", () => {
    expect(
      isPrBaseOtherThanTarget({
        prBaseName: "release",
        targetRef: "origin/main",
        prBaseNames: { "origin/main": "main" },
      }),
    ).toBe(true);
  });

  it("keeps a local target whose first segment names no remote", () => {
    expect(
      isPrBaseOtherThanTarget({
        prBaseName: "feature/login",
        targetRef: "feature/login",
        prBaseNames: { "feature/login": "feature/login" },
      }),
    ).toBe(false);
  });

  it("reads a jj target bookmark's base from the backend", () => {
    expect(
      isPrBaseOtherThanTarget({ prBaseName: "main", targetRef: "main@origin", prBaseNames: { "main@origin": "main" } }),
    ).toBe(false);
  });

  it("is true while the backend has not named the target's base", () => {
    expect(isPrBaseOtherThanTarget({ prBaseName: "main", targetRef: "origin/main", prBaseNames: {} })).toBe(true);
  });
});

describe("findTargetForPrBase", () => {
  it("finds the remote-tracking candidate that opens pull requests into the base", () => {
    expect(
      findTargetForPrBase({
        prBaseName: "release/2.0",
        targetBranches: ["origin/main", "origin/release/2.0"],
        prBaseNames: { "origin/main": "main", "origin/release/2.0": "release/2.0" },
      }),
    ).toBe("origin/release/2.0");
  });

  it("prefers a remote bookmark to the local bookmark of the same name", () => {
    expect(
      findTargetForPrBase({
        prBaseName: "main",
        targetBranches: ["main", "main@origin"],
        prBaseNames: { main: "main", "main@origin": "main" },
      }),
    ).toBe("main@origin");
  });

  it("takes a local candidate when no remote one opens pull requests into the base", () => {
    expect(
      findTargetForPrBase({
        prBaseName: "release/1.0",
        targetBranches: ["main", "release/1.0"],
        prBaseNames: { main: "main", "release/1.0": "release/1.0" },
      }),
    ).toBe("release/1.0");
  });

  it("finds nothing when no candidate opens pull requests into the base", () => {
    expect(
      findTargetForPrBase({
        prBaseName: "login",
        targetBranches: ["feature/login"],
        prBaseNames: { "feature/login": "feature/login" },
      }),
    ).toBeNull();
  });
});
