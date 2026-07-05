import { IconButton, Tooltip } from "@radix-ui/themes";
import { CheckIcon, CopyIcon, WrapText } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { memo, useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";

import styles from "./ChatTable.module.scss";
import { skipNextScrollAdjustForItem } from "./hooks/useChatVirtualizer.ts";

type ChatTableProps = {
  children: ReactNode;
};

const COPY_FEEDBACK_DURATION_MS = 1500;
const CONTROL_ICON_SIZE = 14;

/**
 * Wraps a markdown-rendered table in a container with a copy button and a
 * per-table wrap toggle. Tables wrap their cell text by default; the toggle
 * switches an individual table to a horizontally scrollable, no-wrap layout.
 * Wrap state is component-local and resets on remount; this is intentional so
 * toggling one table doesn't resize others on the page (which would cause
 * large layout shifts in the virtualized chat).
 */
export const ChatTable = memo(({ children }: ChatTableProps): ReactElement => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [isCopied, setIsCopied] = useState(false);
  const [isWrapping, setIsWrapping] = useState(true);

  const updateScrollState = useCallback((): void => {
    const el = wrapperRef.current;
    if (!el) return;
    if (isWrapping) {
      el.style.setProperty("--fade-left", "0px");
      el.style.setProperty("--fade-right", "0px");
      return;
    }
    const maxFade = 24;
    const distanceFromRight = el.scrollWidth - el.clientWidth - el.scrollLeft;
    el.style.setProperty("--fade-left", `${Math.min(el.scrollLeft, maxFade)}px`);
    el.style.setProperty("--fade-right", `${Math.min(distanceFromRight, maxFade)}px`);
  }, [isWrapping]);

  useEffect(() => {
    updateScrollState();
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new ResizeObserver(updateScrollState);
    observer.observe(el);
    return (): void => {
      observer.disconnect();
    };
  }, [updateScrollState]);

  // Clear the pending copy-feedback timer only on unmount. Keeping this
  // separate from the ResizeObserver effect above avoids cancelling an
  // in-flight timer whenever `updateScrollState` changes (e.g. on wrap toggle).
  useEffect(() => {
    return (): void => {
      clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopy = useCallback((): void => {
    if (!tableRef.current) return;
    const rows = tableRef.current.querySelectorAll("tr");
    const mdRows: Array<string> = [];
    let isFirstRow = true;
    for (const row of rows) {
      const cells = Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent ?? "");
      mdRows.push(`| ${cells.join(" | ")} |`);
      if (isFirstRow) {
        mdRows.push(`| ${cells.map(() => "---").join(" | ")} |`);
        isFirstRow = false;
      }
    }
    navigator.clipboard.writeText(mdRows.join("\n"));
    setIsCopied(true);
    clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setIsCopied(false), COPY_FEEDBACK_DURATION_MS);
  }, []);

  const handleToggleWrap = useCallback((): void => {
    // The chat virtualizer compensates for size changes of items above the
    // viewport by bumping `scrollTop`. That keeps streaming content stable
    // but pulls the view away from the click point on a deliberate toggle.
    // Tell the virtualizer to skip the next compensation for THIS specific
    // virtual item only (looked up via the closest `[data-index]` ancestor
    // set in ChatInterface). One-shot, consume-on-match — no timers.
    const virtualItemEl = tableRef.current?.closest<HTMLElement>("[data-index]");
    const indexAttr = virtualItemEl?.dataset.index;
    if (indexAttr != null) {
      const index = Number(indexAttr);
      if (Number.isFinite(index)) {
        skipNextScrollAdjustForItem(index);
      }
    }
    setIsWrapping((prev) => !prev);
  }, []);

  return (
    <div className={styles.tableOuter}>
      <div
        ref={wrapperRef}
        className={`${styles.tableWrapper} ${isWrapping ? styles.wrap : styles.scroll}`}
        onScroll={updateScrollState}
      >
        <table ref={tableRef} className={styles.table} data-testid={ElementIds.ALPHA_CHAT_TABLE}>
          {children}
        </table>
      </div>
      <div className={styles.controls}>
        <Tooltip content={isWrapping ? "Switch to scroll" : "Switch to wrap"}>
          <IconButton
            variant="ghost"
            size="1"
            className={`${styles.controlButton} ${isWrapping ? styles.activeControl : ""}`}
            onClick={handleToggleWrap}
            aria-label={isWrapping ? "Switch to scroll" : "Switch to wrap"}
            data-testid={ElementIds.ALPHA_CHAT_TABLE_WRAP_TOGGLE}
          >
            <WrapText size={CONTROL_ICON_SIZE} />
          </IconButton>
        </Tooltip>
        <Tooltip content="Copy table">
          <IconButton
            variant="ghost"
            size="1"
            className={styles.controlButton}
            onClick={handleCopy}
            aria-label="Copy table"
          >
            {isCopied ? <CheckIcon size={CONTROL_ICON_SIZE} /> : <CopyIcon size={CONTROL_ICON_SIZE} />}
          </IconButton>
        </Tooltip>
      </div>
    </div>
  );
});
