import { Anchor as PopoverAnchor } from "@radix-ui/react-popover";
import { Popover } from "@radix-ui/themes";
import { type CSSProperties, type KeyboardEvent, type ReactElement, useRef, useState } from "react";

import { ElementIds } from "~/api";

import styles from "./AlphaContextSummary.module.scss";
import { AlphaMarkdownBlock } from "./AlphaMarkdownBlock.tsx";

const POPOVER_STYLE: CSSProperties = {
  padding: 0,
  width: 560,
  // Cap to the viewport so the popover never overflows a narrow (mobile) screen.
  // Desktop is unaffected: 560px is far below the cap on any normal window.
  maxWidth: "calc(100vw - 24px)",
  maxHeight: 480,
};

const HINT_PREVIEW_LENGTH = 80;

export const AlphaContextSummary = ({ text, label }: { text: string; label: string }): ReactElement => {
  const [isOpen, setIsOpen] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);

  const toggle = (): void => setIsOpen((prev) => !prev);
  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle();
    }
  };

  return (
    <Popover.Root open={isOpen} onOpenChange={setIsOpen}>
      <PopoverAnchor>
        <div
          ref={anchorRef}
          role="button"
          tabIndex={0}
          aria-expanded={isOpen}
          className={`${styles.row} ${isOpen ? styles.rowOpen : ""}`}
          onClick={toggle}
          onKeyDown={handleKeyDown}
          data-testid={ElementIds.CONTEXT_SUMMARY}
        >
          <span className={styles.pillLabel} data-testid={ElementIds.CONTEXT_SUMMARY_HEADER}>
            {label}
          </span>
          <span className={styles.pillHint}>{text.slice(0, HINT_PREVIEW_LENGTH)}</span>
        </div>
      </PopoverAnchor>
      <Popover.Content
        side="bottom"
        sideOffset={4}
        align="start"
        collisionPadding={16}
        className={styles.popoverContent}
        onOpenAutoFocus={(e): void => e.preventDefault()}
        onPointerDownOutside={(e): void => {
          if (anchorRef.current?.contains(e.target as Node)) e.preventDefault();
        }}
        style={POPOVER_STYLE}
      >
        <div className={styles.popoverBody}>
          <div className={styles.header}>
            <span className={styles.headerLabel}>{label}</span>
          </div>
          <div className={styles.content}>
            <AlphaMarkdownBlock content={text} />
          </div>
        </div>
      </Popover.Content>
    </Popover.Root>
  );
};
