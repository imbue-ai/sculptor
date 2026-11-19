import { describe, expect, it } from "vitest";

import { resolveSelectedRevisionCommitId } from "./revisionSelection.ts";

const SELECTED = { changeId: "kxqpmzvy", commitId: "aaaaaaaa" };

describe("resolveSelectedRevisionCommitId", () => {
  it("keeps the selected commit while it is still listed", () => {
    expect(
      resolveSelectedRevisionCommitId({
        selection: SELECTED,
        revisions: [
          { changeId: "kxqpmzvy", commitId: "aaaaaaaa" },
          { changeId: "kxqpmzvy", commitId: "bbbbbbbb" },
        ],
      }),
    ).toBe("aaaaaaaa");
  });

  it("follows the change to the commit jj rewrote it to", () => {
    expect(
      resolveSelectedRevisionCommitId({
        selection: SELECTED,
        revisions: [
          { changeId: "zzzzzzzz", commitId: "cccccccc" },
          { changeId: "kxqpmzvy", commitId: "bbbbbbbb" },
        ],
      }),
    ).toBe("bbbbbbbb");
  });

  it("selects nothing once the change has left the list", () => {
    expect(
      resolveSelectedRevisionCommitId({
        selection: SELECTED,
        revisions: [{ changeId: "zzzzzzzz", commitId: "cccccccc" }],
      }),
    ).toBeNull();
  });

  it("keeps the selected commit until the revisions load", () => {
    expect(resolveSelectedRevisionCommitId({ selection: SELECTED, revisions: undefined })).toBe("aaaaaaaa");
  });
});
