// jj's own logs show at least this many characters of a change id, and this
// many of a commit id.
const SHORT_CHANGE_ID_MIN_LENGTH = 8;
const SHORT_COMMIT_ID_LENGTH = 8;

/**
 * The short form of a jj change id, as jj's logs show it, split where its
 * shortest unique prefix ends so the prefix can be emphasised.
 */
export const shortChangeId = (inputs: {
  changeId: string;
  uniquePrefixLength: number;
}): { uniquePrefix: string; rest: string } => {
  const length = Math.max(SHORT_CHANGE_ID_MIN_LENGTH, inputs.uniquePrefixLength);
  return {
    uniquePrefix: inputs.changeId.slice(0, inputs.uniquePrefixLength),
    rest: inputs.changeId.slice(inputs.uniquePrefixLength, length),
  };
};

/** The short form of a jj commit id, as jj's logs show it. */
export const shortCommitId = (commitId: string): string => commitId.slice(0, SHORT_COMMIT_ID_LENGTH);
