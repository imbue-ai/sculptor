/**
 * Append a transcribed segment to the draft with the spacing a person would
 * type: one separating space when needed, no trailing whitespace, and a blank
 * segment leaves the draft untouched.
 */
export const appendTranscript = (inputs: { draft: string; segment: string }): string => {
  const trimmedSegment = inputs.segment.trim();
  if (trimmedSegment === "") {
    return inputs.draft;
  }

  if (inputs.draft === "" || /\s$/.test(inputs.draft)) {
    return `${inputs.draft}${trimmedSegment}`;
  }
  return `${inputs.draft} ${trimmedSegment}`;
};
