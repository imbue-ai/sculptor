import type { RevisionInfo } from "~/api";

/** A revision for the Revisions panel stories, an hour old with one file changed. */
export const makeStoryRevision = (
  overrides: Partial<RevisionInfo> & Pick<RevisionInfo, "changeId" | "commitId">,
): RevisionInfo => ({
  changeIdPrefixLength: 2,
  description: "",
  authorName: "Ada Lovelace",
  timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  parentCommitIds: ["9876543210fedcba9876543210fedcba98765432"],
  files: [{ path: "src/login/LoginForm.tsx", status: "M", oldPath: null, additions: 24, deletions: 3 }],
  bookmarks: [],
  isWorkingCopy: false,
  isEmpty: false,
  hasConflict: false,
  isDivergent: false,
  ...overrides,
});
