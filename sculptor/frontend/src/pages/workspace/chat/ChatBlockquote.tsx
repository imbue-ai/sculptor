import { IconButton, Tooltip } from "@radix-ui/themes";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { memo, useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";

import styles from "./ChatBlockquote.module.scss";

// How long the copy button shows the "copied" checkmark before reverting.
const COPY_FEEDBACK_DURATION_MS = 1500;
const COPY_ICON_SIZE_PX = 14;

type ChatBlockquoteProps = {
  children: ReactNode;
};

/**
 * Wraps a markdown blockquote with a hover-revealed copy button. The copy
 * action emits the blockquote text with a `> ` prefix on each line, so the
 * result round-trips back to markdown.
 */
export const ChatBlockquote = memo(({ children }: ChatBlockquoteProps): ReactElement => {
  const quoteRef = useRef<HTMLQuoteElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
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
    copyTimerRef.current = setTimeout(() => setIsCopied(false), COPY_FEEDBACK_DURATION_MS);
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
          {isCopied ? <CheckIcon size={COPY_ICON_SIZE_PX} /> : <CopyIcon size={COPY_ICON_SIZE_PX} />}
        </IconButton>
      </Tooltip>
    </div>
  );
});
