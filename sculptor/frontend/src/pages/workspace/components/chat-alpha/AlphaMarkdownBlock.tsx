import { useSetAtom } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { Children, createElement, memo, useCallback, useMemo, useRef } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkEmoji from "remark-emoji";
import remarkGfm from "remark-gfm";

import { ElementIds } from "~/api";
import type { EntityType } from "~/components/EntityMentionSuggestion";
import { MentionChip } from "~/components/MentionChip";
import type { SkillType } from "~/components/skillBadge";
import { openFileViewTabAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { lineRangeFromStrings, spotlightScopeFromStrings } from "~/pages/workspace/components/diffPanel/types.ts";
import { useWorkspaceCodePath } from "~/pages/workspace/hooks/useWorkspaceCodePath.ts";

import { AlphaBlockquote } from "./AlphaBlockquote.tsx";
import { AlphaCodeBlock } from "./AlphaCodeBlock.tsx";
import styles from "./AlphaMarkdownBlock.module.scss";
import { AlphaTable } from "./AlphaTable.tsx";
import { useChatTask } from "./ChatTaskContext.tsx";
import { isFilePath, isPathInWorkspace, resolveNavPath, splitFilePathSegments } from "./filePathLinkify.ts";
import type { HighlightState } from "./highlightTextMatches.tsx";
import { highlightTextInTree } from "./highlightTextMatches.tsx";
import { rehypeCursor, type RehypeCursorOptions } from "./rehypeCursor.ts";
import { remarkPreserveOrderedListMarkers } from "./remarkPreserveOrderedListMarkers.ts";
import { StreamingCursor } from "./StreamingCursor.tsx";

const handleFilePathKeyDown = (e: React.KeyboardEvent, navPath: string, onClick: (path: string) => void): void => {
  if (e.key === "Enter" || e.key === " ") {
    e.stopPropagation();
    e.preventDefault();
    onClick(navPath);
  }
};

/**
 * Walk React children, replacing string nodes that contain file paths with a
 * mix of plain text and clickable `<span>` elements.
 */
const linkifyChildren = (
  children: ReactNode,
  workspaceCodePath: string | null,
  onPathClick: (navPath: string) => void,
): ReactNode =>
  Children.map(children, (child) => {
    if (typeof child !== "string") return child;

    const segments = splitFilePathSegments(child, workspaceCodePath);
    if (segments.length === 1 && segments[0].kind === "text") return child;

    return segments.map((segment, i) => {
      if (segment.kind === "text") return segment.value;
      return (
        <span
          key={i}
          role="link"
          tabIndex={0}
          className={styles.filePathLink}
          data-testid={ElementIds.ALPHA_CHAT_FILE_PATH_LINK}
          onClick={(e): void => {
            e.stopPropagation();
            onPathClick(segment.navPath);
          }}
          onKeyDown={(e): void => handleFilePathKeyDown(e, segment.navPath, onPathClick)}
        >
          {segment.value}
        </span>
      );
    });
  });

// Tiptap's `renderMarkdown` for the Mention extension serializes @-mentions
// and /-skills as `<span data-sculptor-node ...>...</span>` (see
// TipTapConfig.ts). That HTML reaches the message text we render in chat
// history; remark-parse treats it as literal text, so without pre-processing
// the raw tags appear as visible text in the user message bubble. We replace
// each span with a text sentinel that survives markdown parsing and swap it
// back in for a <MentionChip> during children traversal. The sentinel reuses
// the entity-mention `+[...]` shape — known to survive remark-gfm intact —
// with a type prefix that can't collide with real entity types. The
// placeholder value is a plain letter so remark-gfm doesn't interpret
// adjacent sentinels' delimiter characters as emphasis markers (e.g.
// `|_]..|_]` previously paired the `_` as italic, breaking multi-chip
// messages).
const SCULPTOR_NODE_SPAN_RE = /<span\s+data-sculptor-node(?:\s+[^>]*?)?>([\s\S]*?)<\/span>/g;
const ENTITY_MENTION_PATTERN = String.raw`\+\[([^:]+):([^|]+)\|([^\]]+)\]`;
const SCULPTOR_TOKEN_PATTERN = String.raw`\+\[sculptorChip:(\d+)\|x\]`;

// Combined regex: alternation between the sculptor sentinel and the generic
// entity token. Match groups:
//   [1]      sculptor index (when sculptor token matched)
//   [2/3/4]  entity type / id / display name (when entity matched)
// The patterns are mutually exclusive in practice — the sculptor type marker
// `sculptorChip` is reserved. Hoisted to module scope so it isn't rebuilt for
// every string child on every streaming tick; `matchAll` clones the regex, so
// sharing one global instance across calls is safe.
const CHIP_TOKEN_RE = new RegExp(`(?:${SCULPTOR_TOKEN_PATTERN})|(?:${ENTITY_MENTION_PATTERN})`, "g");

type ParsedSculptorSpan = {
  id: string;
  skillDescription: string | null;
  skillType: SkillType | null;
  spotlightFile?: string | null;
  spotlightPreviousStart?: string | null;
  spotlightPreviousEnd?: string | null;
  spotlightCurrentStart?: string | null;
  spotlightCurrentEnd?: string | null;
  spotlightPreviousSnippet?: string | null;
  spotlightCurrentSnippet?: string | null;
  spotlightSnippetCapturedAt?: string | null;
  spotlightScope?: string | null;
  spotlightCommitHash?: string | null;
  spotlightCapturedBranch?: string | null;
  spotlightCapturedHeadCommit?: string | null;
};

const extractSculptorSpans = (content: string): { processedContent: string; spans: Array<ParsedSculptorSpan> } => {
  if (!content.includes("data-sculptor-node")) {
    return { processedContent: content, spans: [] };
  }
  const spans: Array<ParsedSculptorSpan> = [];
  const processedContent = content.replace(SCULPTOR_NODE_SPAN_RE, (match) => {
    const doc = new DOMParser().parseFromString(match, "text/html");
    const span = doc.querySelector("span[data-sculptor-node]");
    if (!span) return match;
    const index = spans.length;
    spans.push({
      id: span.textContent ?? "",
      skillDescription: span.getAttribute("data-skill-description"),
      skillType: span.getAttribute("data-skill-type") as SkillType | null,
      spotlightFile: span.getAttribute("data-spotlight-file"),
      spotlightPreviousStart: span.getAttribute("data-spotlight-previous-start"),
      spotlightPreviousEnd: span.getAttribute("data-spotlight-previous-end"),
      spotlightCurrentStart: span.getAttribute("data-spotlight-current-start"),
      spotlightCurrentEnd: span.getAttribute("data-spotlight-current-end"),
      spotlightPreviousSnippet: span.getAttribute("data-spotlight-previous-snippet"),
      spotlightCurrentSnippet: span.getAttribute("data-spotlight-current-snippet"),
      spotlightSnippetCapturedAt: span.getAttribute("data-spotlight-snippet-captured-at"),
      spotlightScope: span.getAttribute("data-spotlight-scope"),
      spotlightCommitHash: span.getAttribute("data-spotlight-commit-hash"),
      spotlightCapturedBranch: span.getAttribute("data-spotlight-captured-branch"),
      spotlightCapturedHeadCommit: span.getAttribute("data-spotlight-captured-head-commit"),
    });
    return `+[sculptorChip:${index}|x]`;
  });
  return { processedContent, spans };
};

// Combined chip-rendering pass: in one walk over each string child, scan
// for both the `+[sculptorChip:N|x]` sentinel (which `extractSculptorSpans`
// inserted in place of `<span data-sculptor-node>` markup) AND the entity-
// mention `+[type:id|displayName]` token. Doing this as TWO sequential
// `Children.map` passes used to silently drop the entity chips: the first
// pass returns a Fragment, and `Children.map` treats a Fragment as one
// opaque child — the second pass would skip the strings buried inside.
const renderChips = (children: ReactNode, spans: ReadonlyArray<ParsedSculptorSpan>): ReactNode =>
  Children.map(children, (child) => {
    if (typeof child !== "string") return child;
    if (!child.includes("+[")) return child;

    const parts: Array<string | ReactElement> = [];
    let lastIndex = 0;
    for (const match of child.matchAll(CHIP_TOKEN_RE)) {
      const matchIndex = match.index ?? 0;
      if (matchIndex > lastIndex) {
        parts.push(child.slice(lastIndex, matchIndex));
      }

      if (match[1] !== undefined) {
        // Sculptor sentinel — restore from the captured span metadata. Skip
        // when no matching span entry exists (defensive; e.g. mismatched
        // sentinel slipped past extraction).
        const parsed = spans[parseInt(match[1], 10)];
        if (parsed) {
          if (parsed.spotlightFile) {
            parts.push(
              <MentionChip
                key={`spotlight-${matchIndex}`}
                kind="spotlight"
                file={parsed.spotlightFile}
                previousFileLines={lineRangeFromStrings(parsed.spotlightPreviousStart, parsed.spotlightPreviousEnd)}
                currentFileLines={lineRangeFromStrings(parsed.spotlightCurrentStart, parsed.spotlightCurrentEnd)}
                scope={spotlightScopeFromStrings(parsed.spotlightScope, parsed.spotlightCommitHash)}
                previousSnippet={parsed.spotlightPreviousSnippet ?? undefined}
                currentSnippet={parsed.spotlightCurrentSnippet ?? undefined}
                snippetCapturedAt={parsed.spotlightSnippetCapturedAt ?? undefined}
                capturedBranch={parsed.spotlightCapturedBranch ?? undefined}
                capturedHeadCommit={parsed.spotlightCapturedHeadCommit ?? undefined}
              />,
            );
          } else {
            parts.push(
              <MentionChip
                key={`sculptor-${matchIndex}`}
                id={parsed.id}
                skillDescription={parsed.skillDescription}
                skillType={parsed.skillType}
              />,
            );
          }
        }
      } else {
        parts.push(
          <MentionChip
            key={`entity-${matchIndex}`}
            kind="entity"
            entityType={match[2] as EntityType}
            entityId={match[3]}
            entityDisplayName={match[4]}
          />,
        );
      }
      lastIndex = matchIndex + match[0].length;
    }
    if (parts.length === 0) return child;
    if (lastIndex < child.length) {
      parts.push(child.slice(lastIndex));
    }
    return <>{parts}</>;
  });

/**
 * Wraps a render callback that reads and mutates `highlightState`, making the
 * mutation idempotent under React StrictMode. StrictMode double-invokes the
 * markdown component overrides; the first call advances the counter, so the
 * second call would see a stale value and mis-mark occurrences. We track the
 * children reference and the pre-call counter; if we're re-invoked with the
 * same children, we rewind the counter before running the callback again.
 *
 * Each guard instance keeps its own `prev*` state, so create separate guards
 * for overrides that might be called in interleaved order (e.g. block-level
 * tags vs. code blocks).
 */
const createOccurrenceGuard = (
  highlightState: HighlightState,
): ((children: ReactNode, render: () => ReactElement) => ReactElement) => {
  let prevChildren: ReactNode = null;
  let prevOccurrenceIndex = 0;
  return (children, render) => {
    if (children === prevChildren) {
      highlightState.occurrenceIndex = prevOccurrenceIndex;
    }
    prevChildren = children;
    prevOccurrenceIndex = highlightState.occurrenceIndex;
    return render();
  };
};

type AlphaMarkdownBlockProps = {
  content: string;
  enableFileLinks?: boolean;
  searchQuery?: string;
  /** Which occurrence (0-based, across the entire message) is the active match. -1 for none. */
  activeOccurrenceIndex?: number;
  /** Show a blinking block cursor after the last character. */
  showCursor?: boolean;
};

export const AlphaMarkdownBlock = memo(
  ({
    content,
    enableFileLinks = true,
    searchQuery,
    activeOccurrenceIndex = -1,
    showCursor = false,
  }: AlphaMarkdownBlockProps): ReactElement => {
    const { workspaceId: workspaceID } = useChatTask();
    const workspaceCodePath = useWorkspaceCodePath(workspaceID);
    const openFileViewTab = useSetAtom(openFileViewTabAtom);

    const handlePathClick = useCallback(
      (navPath: string): void => {
        openFileViewTab({ workspaceId: workspaceID, filePath: navPath });
      },
      [openFileViewTab, workspaceID],
    );

    const { processedContent, spans: sculptorSpans } = useMemo(() => extractSculptorSpans(content), [content]);

    // Stash `sculptorSpans` in a ref so it can change every render (it's a
    // fresh array each tick of streaming) without invalidating the
    // `components` memo below. If `components` rebuilt on every token, every
    // tag override would be a new function reference, and react-markdown
    // would treat AlphaTable / AlphaCodeBlock as new component types and
    // unmount/remount them — wiping CSS :hover state and causing the copy
    // button to flicker as the agent streams.
    const sculptorSpansRef = useRef(sculptorSpans);
    sculptorSpansRef.current = sculptorSpans;

    // Mutable highlight state for tracking the occurrence index across all
    // component overrides within a single render pass. Lives in a ref so the
    // `components` memo can stay stable across streaming ticks (see the
    // `sculptorSpansRef` note above) while we still reset the counter to 0
    // before every render — done inline below — so highlights count from
    // zero each pass.
    //
    // react-markdown invokes our component overrides in DOM order while it
    // walks the parsed AST; we don't own that walk, so counting match
    // occurrences *across* blocks requires threading a mutable counter through
    // the closures. The alternative — re-parsing the markdown ourselves to
    // pre-compute offsets — would duplicate react-markdown's work for little
    // gain. The `createOccurrenceGuard` helper wraps each call in a check
    // that restores the counter if StrictMode double-invokes the override
    // with the same children reference.
    const highlightStateRef = useRef<HighlightState>({ occurrenceIndex: 0 });
    highlightStateRef.current.occurrenceIndex = 0;

    const components = useMemo<Components>(() => {
      const highlightState = highlightStateRef.current;
      const guardBlock = createOccurrenceGuard(highlightState);
      const guardCode = createOccurrenceGuard(highlightState);

      const h = (tag: string, children: ReactNode, props: Record<string, unknown>): ReactElement => {
        if (!searchQuery) return createElement(tag, props, children);
        return guardBlock(children, () => {
          const { node } = highlightTextInTree(children, searchQuery, activeOccurrenceIndex, highlightState);
          return createElement(tag, props, node);
        });
      };

      const process = (children: ReactNode): ReactNode => renderChips(children, sculptorSpansRef.current);

      return {
        p: ({ children, node: _n, ...rest }): ReactElement => {
          const processed = process(children);
          if (enableFileLinks && !searchQuery) {
            return <p {...rest}>{linkifyChildren(processed, workspaceCodePath, handlePathClick)}</p>;
          }
          return h("p", processed, rest);
        },
        li: ({ children, node: _n, ...rest }): ReactElement => {
          const processed = process(children);
          if (enableFileLinks && !searchQuery) {
            return <li {...rest}>{linkifyChildren(processed, workspaceCodePath, handlePathClick)}</li>;
          }
          return h("li", processed, rest);
        },
        h1: ({ children, node: _n, ...rest }): ReactElement => h("h1", process(children), rest),
        h2: ({ children, node: _n, ...rest }): ReactElement => h("h2", process(children), rest),
        h3: ({ children, node: _n, ...rest }): ReactElement => h("h3", process(children), rest),
        h4: ({ children, node: _n, ...rest }): ReactElement => h("h4", process(children), rest),
        h5: ({ children, node: _n, ...rest }): ReactElement => h("h5", process(children), rest),
        h6: ({ children, node: _n, ...rest }): ReactElement => h("h6", process(children), rest),
        td: ({ children, node: _n, ...rest }): ReactElement => h("td", process(children), rest),
        th: ({ children, node: _n, ...rest }): ReactElement => h("th", process(children), rest),
        blockquote: ({ children, node: _n }): ReactElement => {
          const processed = process(children);
          if (!searchQuery) return <AlphaBlockquote>{processed}</AlphaBlockquote>;
          return guardBlock(processed, () => {
            const { node } = highlightTextInTree(processed, searchQuery, activeOccurrenceIndex, highlightState);
            return <AlphaBlockquote>{node}</AlphaBlockquote>;
          });
        },
        code: ({ children, className }): ReactElement => {
          if (!children) {
            return <></>;
          }
          const text = children.toString();
          // react-markdown appends a trailing newline to fenced code block content
          // but not to inline `code` spans, so we use that to distinguish the two.
          const isInline = text.slice(-1) !== "\n";

          if (isInline) {
            if (enableFileLinks && isFilePath(text) && isPathInWorkspace(text, workspaceCodePath)) {
              const navPath = resolveNavPath(text, workspaceCodePath);
              return (
                <span
                  role="link"
                  tabIndex={0}
                  className={styles.filePathCodeLink}
                  data-testid={ElementIds.ALPHA_CHAT_FILE_PATH_LINK}
                  onClick={(e): void => {
                    e.stopPropagation();
                    handlePathClick(navPath);
                  }}
                  onKeyDown={(e): void => handleFilePathKeyDown(e, navPath, handlePathClick)}
                >
                  <code className={styles.inlineCode}>{children}</code>
                </span>
              );
            }
            return <code className={styles.inlineCode}>{children}</code>;
          }

          return guardCode(children, () => {
            // Count search matches in the code content so the shared
            // occurrence counter stays in sync with findMatches (which
            // counts code content as a separate segment).
            let codeActiveIndex = -1;
            if (searchQuery) {
              const lowerQuery = searchQuery.toLowerCase();
              const lowerText = text.toLowerCase();
              let matchCount = 0;
              let pos = 0;
              while (pos < lowerText.length) {
                const idx = lowerText.indexOf(lowerQuery, pos);
                if (idx === -1) break;
                if (highlightState.occurrenceIndex + matchCount === activeOccurrenceIndex) {
                  codeActiveIndex = matchCount;
                }
                matchCount++;
                pos = idx + 1;
              }
              highlightState.occurrenceIndex += matchCount;
            }

            // Extract language from className (e.g. "language-python" → "python")
            const language = className?.replace("language-", "");
            return (
              <AlphaCodeBlock
                content={text}
                language={language}
                searchQuery={searchQuery}
                activeOccurrenceIndex={codeActiveIndex}
              />
            );
          });
        },
        table: ({ children }): ReactElement => {
          return <AlphaTable>{children}</AlphaTable>;
        },
        a: ({ children, href }): ReactElement => {
          return (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          );
        },
        // Suppress image rendering — the backend extracts <img> tags into
        // FileBlocks rendered via the FilePreview component.
        img: (): ReactElement => <></>,
        "streaming-cursor": (): ReactElement => <StreamingCursor />,
      };
    }, [searchQuery, activeOccurrenceIndex, enableFileLinks, workspaceCodePath, handlePathClick]);

    const rehypePlugins = useMemo(
      (): Array<[typeof rehypeCursor, RehypeCursorOptions]> => [[rehypeCursor, { enabled: showCursor }]],
      [showCursor],
    );

    return (
      <div className={styles.markdownBlock}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkEmoji, remarkPreserveOrderedListMarkers]}
          rehypePlugins={rehypePlugins}
          components={components}
        >
          {processedContent}
        </ReactMarkdown>
      </div>
    );
  },
);
