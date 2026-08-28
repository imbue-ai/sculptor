import { IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import { memo, useCallback, useEffect, useRef, useState } from "react";

import { themeCodeThemeAtom } from "~/common/state/atoms/themeBuilder.ts";
import { getShikiThemes } from "~/common/theme/shikiThemes.ts";

import styles from "./AlphaCodeBlock.module.scss";
import { highlightTextInTree } from "./highlightTextMatches.tsx";
import type { DualThemedToken } from "./shikiHighlighter.ts";
import { highlightCode } from "./shikiHighlighter.ts";

/** How long the copy button shows its "copied" confirmation before reverting. */
const COPY_FEEDBACK_DURATION_MS = 1500;

type AlphaCodeBlockProps = {
  /** The raw code string to display. */
  content: string;
  /** The language identifier from the fenced code block (e.g. "python", "ts"). */
  language?: string;
  /** When set, highlight occurrences of this query in the code output. */
  searchQuery?: string;
  /** Which occurrence (0-based, within this code block) is the active match. -1 for none. */
  activeOccurrenceIndex?: number;
};

/**
 * Renders a fenced code block with syntax highlighting via shiki.
 *
 * Highlighting is async (grammar loading), so the block renders plain text
 * first and swaps in colored tokens once ready.
 */
export const AlphaCodeBlock = memo(
  ({ content, language, searchQuery, activeOccurrenceIndex = -1 }: AlphaCodeBlockProps): ReactElement => {
    const [tokens, setTokens] = useState<ReadonlyArray<ReadonlyArray<DualThemedToken>> | null>(null);
    const [isCopied, setIsCopied] = useState(false);
    const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
    const codeTheme = useAtomValue(themeCodeThemeAtom);
    const themes = getShikiThemes(codeTheme);

    useEffect(() => {
      return (): void => clearTimeout(copyTimerRef.current);
    }, []);

    const handleCopy = useCallback((): void => {
      navigator.clipboard.writeText(content.trimEnd());
      setIsCopied(true);
      clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setIsCopied(false), COPY_FEEDBACK_DURATION_MS);
    }, [content]);

    useEffect(() => {
      let isStale = false;

      if (language) {
        highlightCode(content, language, themes).then(
          (result) => {
            if (!isStale) setTokens(result);
          },
          () => {
            // Grammar or theme failed to load — fall back to plain text.
            if (!isStale) setTokens(null);
          },
        );
      } else {
        setTokens(null);
      }

      return (): void => {
        isStale = true;
      };
    }, [content, language, themes]);

    // Render tokens inline (not as a component) so highlightTextInTree can
    // walk into the intrinsic <span> elements and apply search highlights.
    // Plain text uses the same line-based <span> structure as highlighted
    // code so the DOM layout is identical before and after highlighting
    // resolves, preventing a height change that would shift virtualizer
    // item positions.
    const codeContent: ReactNode = tokens ? renderTokens(tokens) : renderPlainLines(content);
    const highlighted = searchQuery
      ? highlightTextInTree(codeContent, searchQuery, activeOccurrenceIndex).node
      : codeContent;

    return (
      <div className={styles.codeBlockWrapper}>
        <pre className={styles.codeBlock} data-language={language}>
          <code>{highlighted}</code>
        </pre>
        <Tooltip content="Copy code">
          <IconButton
            variant="ghost"
            size="1"
            className={styles.copyButton}
            onClick={handleCopy}
            aria-label="Copy code"
          >
            {isCopied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
          </IconButton>
        </Tooltip>
      </div>
    );
  },
);

const tokenStyle = (token: DualThemedToken): CSSProperties | undefined => {
  if (!token.lightColor && !token.darkColor) return undefined;
  return { color: `light-dark(${token.lightColor ?? "inherit"}, ${token.darkColor ?? "inherit"})` };
};

/**
 * Renders plain text as line-based <span> elements, matching the DOM
 * structure of renderTokens().  This ensures the code block's height
 * is identical before and after async syntax highlighting resolves,
 * preventing a visible layout shift in the virtualizer.
 */
const renderPlainLines = (content: string): Array<ReactElement> => {
  const lines = content.split("\n");
  return lines.map((line, i) => (
    <span key={i}>
      <span>{line}</span>
      {i < lines.length - 1 ? "\n" : null}
    </span>
  ));
};

/**
 * Renders syntax-highlighted tokens as an array of intrinsic <span> elements.
 * Returns an array (not a component) so that highlightTextInTree can walk
 * into the spans and apply search highlights on top of syntax coloring.
 */
const renderTokens = (tokens: ReadonlyArray<ReadonlyArray<DualThemedToken>>): Array<ReactElement> =>
  tokens.map((line, i) => (
    <span key={i}>
      {line.map((token, j) => (
        <span key={j} style={tokenStyle(token)}>
          {token.content}
        </span>
      ))}
      {i < tokens.length - 1 ? "\n" : null}
    </span>
  ));
