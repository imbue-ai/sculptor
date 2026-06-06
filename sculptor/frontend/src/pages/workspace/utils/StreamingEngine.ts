import type { ChatMessage, TextBlock } from "~/api";
import { isTextBlock } from "~/common/Guards.ts";

type Cursor = {
  blockIndex: number | null;
  offset: number | null;
};

export class StreamingEngine {
  private latestSnapshot: ChatMessage | null = null;
  private cursor: Cursor = {
    blockIndex: null,
    offset: null,
  };

  public updateLatestSnapshot(snapshot: ChatMessage | null): ChatMessage | null {
    const previousSnapshot = this.latestSnapshot;
    this.latestSnapshot = snapshot;

    if (!snapshot) {
      this.cursor = { blockIndex: null, offset: null };
      return null;
    }

    if (!this.isCursorValid() || this.didContentReorderUnderCursor(previousSnapshot, snapshot)) {
      this.alignCursorToSnapshot(snapshot);
    }

    return this.materialize();
  }

  public flush(): ChatMessage | null {
    if (!this.latestSnapshot) {
      this.cursor = { blockIndex: null, offset: null };
      return null;
    }

    this.alignCursorToSnapshot(this.latestSnapshot);
    return this.materialize();
  }

  /**
   * Advances the cursor forward by up to `charsToReveal` characters of text.
   * Non-text blocks are revealed instantly (the cursor skips past them).
   * Returns the materialized ChatMessage reflecting the new cursor position.
   */
  public advanceCursor(charsToReveal: number): ChatMessage | null {
    if (!this.latestSnapshot || charsToReveal <= 0) {
      return this.materialize();
    }

    // If the cursor hasn't been initialized yet, nothing to advance.
    if (this.cursor.blockIndex === null) {
      return this.materialize();
    }

    let remaining = charsToReveal;
    const contentLength = this.latestSnapshot.content.length;

    while (remaining > 0 && this.cursor.blockIndex < contentLength) {
      const block = this.latestSnapshot.content[this.cursor.blockIndex];

      if (this.cursor.offset !== null && isTextBlock(block)) {
        const textBlock = block as TextBlock;
        const available = textBlock.text.length - this.cursor.offset;
        const advance = Math.min(remaining, available);
        this.cursor.offset += advance;
        remaining -= advance;

        // If we consumed the entire text block, try to move to the next block.
        if (this.cursor.offset >= textBlock.text.length) {
          if (this.cursor.blockIndex + 1 < contentLength) {
            this.cursor.blockIndex += 1;
            const nextBlock = this.latestSnapshot.content[this.cursor.blockIndex];
            // When isTailFullyRendered was true, materialize() already showed
            // subsequent text blocks in full.  Start the cursor at their current
            // length so that already-visible content is never regressed.
            this.cursor.offset = isTextBlock(nextBlock) ? (nextBlock as TextBlock).text.length : null;
          } else {
            break; // Last block fully consumed — nothing more to reveal.
          }
        }
      } else {
        // Non-text block: reveal it entirely, move to the next block.
        if (this.cursor.blockIndex + 1 < contentLength) {
          this.cursor.blockIndex += 1;
          const nextBlock = this.latestSnapshot.content[this.cursor.blockIndex];
          // Same rationale: the non-text cursor had isTailFullyRendered = true,
          // so any following text block was already fully visible.
          this.cursor.offset = isTextBlock(nextBlock) ? (nextBlock as TextBlock).text.length : null;
        } else {
          break;
        }
      }
    }

    return this.materialize();
  }

  /** Read-only access to the current snapshot (for word-boundary snapping in the rAF loop). */
  public peekSnapshot(): ChatMessage | null {
    return this.latestSnapshot;
  }

  /** Read-only copy of the current cursor position. */
  public peekCursor(): Readonly<Cursor> {
    return { blockIndex: this.cursor.blockIndex, offset: this.cursor.offset };
  }

  /**
   * Returns the number of unrevealed text characters remaining after the cursor.
   */
  public getBufferSize(): number {
    if (!this.latestSnapshot || this.cursor.blockIndex === null) {
      return 0;
    }

    let total = 0;

    for (let i = this.cursor.blockIndex; i < this.latestSnapshot.content.length; i += 1) {
      const block = this.latestSnapshot.content[i];
      if (isTextBlock(block)) {
        const text = (block as TextBlock).text;
        if (i === this.cursor.blockIndex && this.cursor.offset !== null) {
          total += Math.max(0, text.length - this.cursor.offset);
        } else {
          total += text.length;
        }
      }
    }

    return total;
  }

  private alignCursorToSnapshot(snapshot: ChatMessage): void {
    const tailIndex = this.findTailTextBlockIndex(snapshot);
    if (tailIndex === null) {
      if (snapshot.content.length === 0) {
        this.cursor = { blockIndex: null, offset: null };
        return;
      }
      this.cursor = {
        blockIndex: snapshot.content.length - 1,
        offset: null,
      };
      return;
    }

    const tailBlock = snapshot.content[tailIndex] as TextBlock;
    this.cursor = {
      blockIndex: tailIndex,
      offset: tailBlock.text.length,
    };
  }

  private findTailTextBlockIndex(snapshot: ChatMessage): number | null {
    for (let index = snapshot.content.length - 1; index >= 0; index -= 1) {
      if (isTextBlock(snapshot.content[index])) {
        return index;
      }
    }
    return null;
  }

  private materialize(): ChatMessage | null {
    if (!this.latestSnapshot) {
      return null;
    }

    if (this.cursor.blockIndex === null) {
      return this.latestSnapshot;
    }

    const snapshot = this.latestSnapshot;
    const cursorIndex = this.cursor.blockIndex;
    const activeBlock = snapshot.content[cursorIndex];
    const isTextCursor = this.cursor.offset !== null && isTextBlock(activeBlock);
    const textBlock = isTextCursor ? (activeBlock as TextBlock) : null;
    const safeOffset = isTextCursor && textBlock ? Math.min(this.cursor.offset ?? 0, textBlock.text.length) : null;
    const content: Array<ChatMessage["content"][number]> = [];

    for (let index = 0; index < snapshot.content.length; index += 1) {
      const block = snapshot.content[index];

      if (index === cursorIndex && isTextCursor && safeOffset !== null && textBlock) {
        content.push({
          ...block,
          text: textBlock.text.slice(0, safeOffset),
        });
      } else {
        content.push(block);
      }
    }

    return {
      ...snapshot,
      content,
    };
  }

  /**
   * Detects whether the new snapshot reordered or replaced content under the
   * cursor in a way that would regress already-visible text.
   *
   * ``materialize`` only ever hides content by truncating the cursor's text
   * block to ``offset`` — every other block is shown in full.  ``isCursorValid``
   * keeps the cursor whenever ``offset`` still fits whatever block now sits at
   * ``blockIndex``, but it does not check that it is the SAME block.  When the
   * backend reorders content (e.g. output_processor splices an extracted
   * ``<img>`` FileBlock and its trailing text in front of an already-streamed
   * block, shifting every later index), a different, longer block can slide into
   * the cursor's index and ``offset`` would truncate text that was already fully
   * revealed.
   *
   * Guard against that: if the block now at the cursor index no longer begins
   * with the text we had already revealed there, the content moved out from
   * under the cursor, so realign to the tail (revealing everything) rather than
   * regressing visible content.  A non-text cursor (``offset === null``) never
   * truncates, so it cannot regress and is ignored here.
   */
  private didContentReorderUnderCursor(previous: ChatMessage | null, next: ChatMessage): boolean {
    if (previous === null) {
      return false;
    }
    const index = this.cursor.blockIndex;
    const offset = this.cursor.offset;
    if (index === null || offset === null) {
      return false;
    }
    const previousBlock = previous.content[index];
    const nextBlock = next.content[index];
    if (previousBlock === undefined || !isTextBlock(previousBlock)) {
      return false;
    }

    if (nextBlock === undefined || !isTextBlock(nextBlock)) {
      // The block kind changed at this index; isCursorValid already forces a
      // realign for that case, so nothing extra to do here.
      return false;
    }
    const alreadyRevealed = (previousBlock as TextBlock).text.slice(0, offset);
    return !(nextBlock as TextBlock).text.startsWith(alreadyRevealed);
  }

  private isCursorValid(): boolean {
    if (this.cursor.blockIndex === null) {
      if (this.cursor.offset !== null) {
        return false;
      }

      if (!this.latestSnapshot) {
        return true;
      }

      return this.findTailTextBlockIndex(this.latestSnapshot) === null;
    }

    if (!this.latestSnapshot) {
      return false;
    }

    if (this.cursor.blockIndex < 0 || this.cursor.blockIndex >= this.latestSnapshot.content.length) {
      return false;
    }

    const block = this.latestSnapshot.content[this.cursor.blockIndex];

    if (this.cursor.offset === null) {
      return !isTextBlock(block);
    }

    if (!isTextBlock(block)) {
      return false;
    }

    if (this.cursor.offset < 0) {
      return false;
    }

    const text = (block as TextBlock).text;
    return this.cursor.offset <= text.length;
  }
}

// Multiple chat panels can stream at once now that agents are panels — each
// agent panel owns its own StreamingEngine (REQ-AGENT-4). We track the live
// engines as a set rather than asserting a single global one. Registration is
// idempotent; nothing reads the set externally — it exists only so a future
// global flush/inspection could enumerate active engines.
const activeEngines = new Set<StreamingEngine>();

export const registerEngine = (engine: StreamingEngine): void => {
  activeEngines.add(engine);
};

export const unregisterEngine = (engine: StreamingEngine): void => {
  activeEngines.delete(engine);
};
