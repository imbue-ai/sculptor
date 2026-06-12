import type { ReactElement } from "react";

/**
 * Wrap the first case-insensitive substring match of `query` inside `text`
 * with a highlight span (or the caller-supplied element). Returns the raw
 * text if the query is empty or no match is found.
 *
 * The three mention-style pickers (file, skill, entity) share this call
 * shape — each supplies its own scss-module `highlight` class so the
 * visual treatment stays scoped to the caller.
 */
export const highlightMatch = (
  text: string,
  query: string,
  highlightClassName: string,
  Element: "span" | "strong" = "span",
): ReactElement | string => {
  if (query === "") return text;
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const matchIndex = lowerText.indexOf(lowerQuery);
  if (matchIndex === -1) return text;
  const before = text.slice(0, matchIndex);
  const match = text.slice(matchIndex, matchIndex + query.length);
  const after = text.slice(matchIndex + query.length);
  return (
    <>
      {before}
      <Element className={highlightClassName}>{match}</Element>
      {after}
    </>
  );
};
