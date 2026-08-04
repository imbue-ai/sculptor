/**
 * Append a freshly transcribed segment to the current draft with the same
 * spacing a person would type: the segment is trimmed, then joined to the draft
 * with a single separating space unless the draft already ends in whitespace (or
 * is empty), in which case it is appended directly. A blank segment leaves the
 * draft untouched. No trailing whitespace is added, so the caret-adjacent text
 * reads naturally as more segments arrive.
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
