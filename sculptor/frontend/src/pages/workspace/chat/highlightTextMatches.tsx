import type { ReactElement, ReactNode } from "react";
import { Children, cloneElement, isValidElement } from "react";

export type HighlightState = { occurrenceIndex: number };

/**
 * Walk a React element tree and wrap all case-insensitive occurrences of
 * `query` in <mark> elements. The `activeOccurrenceIndex` determines which
 * specific match gets the "active" styling.
 *
 * Only walks into intrinsic HTML elements (div, p, strong, etc.).
 * Component elements (e.g. ReactMarkdown) are returned as-is because their
 * children props may have type constraints (e.g. must be a string).
 *
 * An optional `externalState` can be passed to share occurrence tracking
 * across multiple calls (e.g. across ReactMarkdown component overrides).
 */
export const highlightTextInTree = (
  node: ReactNode,
  query: string,
  activeOccurrenceIndex: number,
  externalState?: HighlightState,
): { node: ReactNode; matchCount: number } => {
  if (!query) return { node, matchCount: 0 };

  const state = externalState ?? { occurrenceIndex: 0 };
  const startIndex = state.occurrenceIndex;
  const result = walkNode(node, query.toLowerCase(), activeOccurrenceIndex, state);
  return { node: result, matchCount: state.occurrenceIndex - startIndex };
};

const walkNode = (node: ReactNode, lowerQuery: string, activeOccurrence: number, state: HighlightState): ReactNode => {
  if (typeof node === "string") {
    return highlightString(node, lowerQuery, activeOccurrence, state);
  }

  if (typeof node === "number") {
    return highlightString(String(node), lowerQuery, activeOccurrence, state);
  }

  if (isValidElement(node)) {
    // React 19's ReactElement defaults its props to unknown; we only walk
    // intrinsic elements, whose children prop is a plain ReactNode.
    const element = node as ReactElement<{ children?: ReactNode }>;

    // Skip component elements — only walk into intrinsic HTML elements.
    // Component elements (functions/classes) may have type constraints on
    // their children prop (e.g. ReactMarkdown requires a string).
    if (typeof element.type !== "string") return element;

    if (!element.props.children) return element;

    const originalChildren = element.props.children as ReactNode;
    const newChildren = walkChildren(originalChildren, lowerQuery, activeOccurrence, state);
    if (newChildren === originalChildren) return element;

    return cloneElement(element, {}, newChildren);
  }

  if (Array.isArray(node)) {
    return walkChildren(node, lowerQuery, activeOccurrence, state);
  }

  return node;
};

const walkChildren = (
  children: ReactNode,
  lowerQuery: string,
  activeOccurrence: number,
  state: HighlightState,
): ReactNode => {
  let hasChanges = false;
  const result = Children.map(children, (child) => {
    const newChild = walkNode(child, lowerQuery, activeOccurrence, state);
    if (newChild !== child) hasChanges = true;
    return newChild;
  });
  return hasChanges ? result : children;
};

const highlightString = (
  text: string,
  lowerQuery: string,
  activeOccurrence: number,
  state: HighlightState,
): ReactNode => {
  const lowerText = text.toLowerCase();
  const queryLen = lowerQuery.length;
  const parts: Array<ReactNode> = [];
  let pos = 0;

  while (pos < text.length) {
    const idx = lowerText.indexOf(lowerQuery, pos);
    if (idx === -1) break;

    if (idx > pos) {
      parts.push(text.slice(pos, idx));
    }

    const isActive = state.occurrenceIndex === activeOccurrence;
    const className = isActive ? "chatSearchActive" : "chatSearchMatch";
    parts.push(
      <mark key={`m-${idx}`} className={className}>
        {text.slice(idx, idx + queryLen)}
      </mark>,
    );

    state.occurrenceIndex++;
    pos = idx + queryLen;
  }

  if (parts.length === 0) return text;

  if (pos < text.length) {
    parts.push(text.slice(pos));
  }

  return <>{parts}</>;
};
