/**
 * Split an answer string into predefined option labels and custom text.
 *
 * Answers are stored as `[...selectedOptions, customText].join(", ")`.
 * We greedily match complete option labels from the front of the string,
 * trying longest labels first to handle labels that are prefixes of others.
 * Everything remaining after the last matched label is the custom text.
 *
 * This is a heuristic — ideally answers would store structured selections
 * rather than a flat string. But this handles option labels that contain
 * ", " (e.g. "Yes, proceed").
 */
const ANSWER_SEPARATOR = ", ";

export const splitAnswerIntoParts = (
  answerText: string,
  options: ReadonlyArray<{ label: string }>,
): { selectedOptions: Array<string>; customText: string } => {
  const sortedLabels = options.map((opt) => opt.label).sort((a, b) => b.length - a.length);
  const selectedOptions: Array<string> = [];
  let remaining = answerText;

  while (remaining.length > 0) {
    const matched = sortedLabels.find((label) => remaining === label || remaining.startsWith(label + ANSWER_SEPARATOR));
    if (!matched) break;
    selectedOptions.push(matched);
    remaining = remaining === matched ? "" : remaining.slice(matched.length + ANSWER_SEPARATOR.length);
  }

  return { selectedOptions, customText: remaining };
};
