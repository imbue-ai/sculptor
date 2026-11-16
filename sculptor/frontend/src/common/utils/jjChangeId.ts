// jj's own logs show at least this many characters of a change id.
const SHORT_CHANGE_ID_MIN_LENGTH = 8;

/**
 * The short form of a jj change id, as jj's logs show it: at least eight
 * characters, split where its shortest unique prefix ends so the prefix can be
 * emphasised.
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
