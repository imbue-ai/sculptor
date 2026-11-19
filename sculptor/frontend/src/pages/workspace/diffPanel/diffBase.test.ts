import { describe, expect, it } from "vitest";

import { diffBaseCommitId } from "./diffBase.ts";

const WORKING_COPY_PARENT = "1111111111111111111111111111111111111111";
const MERGE_BASE = "2222222222222222222222222222222222222222";

describe("diffBaseCommitId", () => {
  it("takes the uncommitted scope's base from the artifact", () => {
    expect(
      diffBaseCommitId({
        diff: { uncommittedDiffBase: WORKING_COPY_PARENT, targetBranchMergeBase: MERGE_BASE },
        scope: "uncommitted",
      }),
    ).toBe(WORKING_COPY_PARENT);
  });

  it("takes the target scope's base from the artifact's merge base", () => {
    expect(
      diffBaseCommitId({
        diff: { uncommittedDiffBase: WORKING_COPY_PARENT, targetBranchMergeBase: MERGE_BASE },
        scope: "vs-target-branch",
      }),
    ).toBe(MERGE_BASE);
  });

  it("has no base when the artifact names none, as for a merge", () => {
    expect(
      diffBaseCommitId({ diff: { uncommittedDiffBase: "", targetBranchMergeBase: "" }, scope: "uncommitted" }),
    ).toBe(null);
    expect(diffBaseCommitId({ diff: {}, scope: "vs-target-branch" })).toBe(null);
  });

  it("has no base before the diff arrives", () => {
    expect(diffBaseCommitId({ diff: undefined, scope: "uncommitted" })).toBe(null);
  });
});
