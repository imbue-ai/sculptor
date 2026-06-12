import { IconButton, Tooltip } from "@radix-ui/themes";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { memo, useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";

import styles from "./AlphaBlockquote.module.scss";

type AlphaBlockquoteProps = {
  children: ReactNode;
};

/**
 * Wraps a markdown blockquote with a hover-revealed copy button. The copy
 * action emits the blockquote text with a `> ` prefix on each line, so the
 * result round-trips back to markdown.
 */
export const AlphaBlockquote = memo(({ children }: AlphaBlockquoteProps): ReactElement => {
  const quoteRef = useRef<HTMLQuoteElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [isCopied, setIsCopied] = useState(false);

  useEffect(() => {
    return (): void => clearTimeout(copyTimerRef.current);
  }, []);

  const handleCopy = useCallback((): void => {
    if (!quoteRef.current) return;
    const text = quoteRef.current.innerText.replace(/\r\n/g, "\n").trim();
    const quoted = text
      .split("\n")
      .map((line) => `> ${line}`)
      .join("\n");
    navigator.clipboard.writeText(quoted);
    setIsCopied(true);
    clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setIsCopied(false), 1500);
  }, []);

  return (
    <div className={styles.blockquoteOuter}>
      <blockquote ref={quoteRef} className={styles.blockquote} data-testid={ElementIds.ALPHA_CHAT_BLOCKQUOTE}>
        {children}
      </blockquote>
      <Tooltip content="Copy quote">
        <IconButton
          variant="ghost"
          size="1"
          className={styles.copyButton}
          onClick={handleCopy}
          aria-label="Copy quote"
          data-testid={ElementIds.ALPHA_CHAT_BLOCKQUOTE_COPY}
        >
          {isCopied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
        </IconButton>
      </Tooltip>
    </div>
  );
});
