import { Box, IconButton, ScrollArea } from "@radix-ui/themes";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkEmoji from "remark-emoji";
import remarkGfm from "remark-gfm";

import { Code } from "./Code";
import styles from "./MarkdownBlock.module.scss";

// How long the copy button shows its "copied" checkmark before reverting.
const COPY_FEEDBACK_DURATION_MS = 1500;

const MemoizedInlineCode = memo(({ children }: { children: ReactNode }): ReactElement => {
  return <Code className={styles.inlineCode}>{children}</Code>;
});

const MemoizedCodeBlock = memo(({ content }: { content: string }): ReactElement => {
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect((): (() => void) => {
    return (): void => {
      if (copyTimeoutRef.current !== undefined) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const handleCopy = useCallback((): void => {
    navigator.clipboard.writeText(content.trimEnd());
    setIsCopied(true);
    if (copyTimeoutRef.current !== undefined) {
      clearTimeout(copyTimeoutRef.current);
    }
    copyTimeoutRef.current = setTimeout((): void => setIsCopied(false), COPY_FEEDBACK_DURATION_MS);
  }, [content]);

  return (
    <div className={styles.codeBlockWrapper}>
      <ScrollArea className={styles.codeBlock} scrollbars="horizontal" type="hover" size="1">
        <div>{content}</div>
      </ScrollArea>
      <IconButton
        variant="ghost"
        size="1"
        className={styles.codeBlockCopyButton}
        onClick={handleCopy}
        title="Copy code"
      >
        {isCopied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
      </IconButton>
    </div>
  );
});

export const MarkdownBlock = memo((props: { content: string }): ReactElement => {
  const components = useMemo<Components>(
    () => ({
      code: (props): ReactElement => {
        const { children } = props;
        if (!children) {
          return <></>;
        }
        const isInline = children.toString().slice(-1) !== "\n";

        if (isInline) {
          return <MemoizedInlineCode>{children}</MemoizedInlineCode>;
        }

        const codeContent = children.toString();

        return <MemoizedCodeBlock content={codeContent} />;
      },
      table: (props): ReactElement => {
        return (
          <ScrollArea scrollbars="horizontal" type="hover" size="1">
            <table {...props} />
          </ScrollArea>
        );
      },
      h1: "h2",
      h2: "h3",
      h3: "strong",
      a: ({ children, href }): ReactElement => {
        return (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        );
      },
      // Suppress image rendering in markdown — the backend extracts <img> tags
      // into FileBlocks rendered via the FilePreview component. Without this,
      // react-markdown would render its own <img> for any image syntax that
      // appears in the text, creating duplicates.
      img: (): ReactElement => <></>,
    }),
    [],
  );

  return (
    <Box className={styles.markdownContainer}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkEmoji]} components={components}>
        {props.content}
      </ReactMarkdown>
    </Box>
  );
});
