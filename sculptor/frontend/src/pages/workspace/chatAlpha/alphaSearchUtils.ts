import type { ChatMessage } from "~/api";
import { isTextBlock, isToolResultBlock, isToolUseBlock } from "~/common/Guards";

export type SearchableBlock = {
  blockIndex: number;
  text: string;
  type: "text" | "code";
};

export type SearchMatch = {
  messageId: string;
  messageIndex: number;
  blockIndex: number;
  startOffset: number;
  length: number;
};

/**
 * Splits raw markdown text into segments, separating fenced code block
 * content from regular markdown text. Code fence markers (```, ~~~, and
 * language identifiers) are excluded so that match counts align with what
 * the renderer actually displays.
 */
export const splitMarkdownSegments = (rawText: string): Array<{ text: string; type: "text" | "code" }> => {
  const segments: Array<{ text: string; type: "text" | "code" }> = [];
  // Match fenced code blocks: opening ``` or ~~~ (with optional language), content, closing fence.
  // Use [ \t]* (horizontal whitespace only) after the closing fence to avoid consuming newlines.
  const fencePattern = /^(```|~~~)[^\n]*\n([\s\S]*?)^\1[ \t]*$/gm;

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = fencePattern.exec(rawText)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ text: rawText.slice(lastIndex, match.index), type: "text" });
    }

    const codeContent = match[2];
    if (codeContent) {
      segments.push({ text: codeContent, type: "code" });
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < rawText.length) {
    segments.push({ text: rawText.slice(lastIndex), type: "text" });
  }

  return segments.length > 0 ? segments : [{ text: rawText, type: "text" }];
};

/**
 * Extracts searchable text blocks from a chat message.
 * Skips tool use and tool result blocks.
 * Splits markdown text at code fences so that fence markers are excluded
 * and code content is tracked separately.
 */
export const extractSearchableText = (message: ChatMessage): Array<SearchableBlock> => {
  const blocks: Array<SearchableBlock> = [];

  message.content.forEach((block, blockIndex) => {
    if (isToolUseBlock(block) || isToolResultBlock(block)) {
      return;
    }

    if (isTextBlock(block)) {
      const segments = splitMarkdownSegments(block.text);
      for (const segment of segments) {
        blocks.push({ blockIndex, text: segment.text, type: segment.type });
      }
    }
  });

  return blocks;
};

/**
 * Finds all case-insensitive substring matches across messages.
 */
export const findMatches = (messages: ReadonlyArray<ChatMessage>, query: string): Array<SearchMatch> => {
  if (!query) return [];

  const lowerQuery = query.toLowerCase();
  const matches: Array<SearchMatch> = [];

  messages.forEach((message, messageIndex) => {
    const blocks = extractSearchableText(message);

    for (const block of blocks) {
      const lowerText = block.text.toLowerCase();
      let startPos = 0;

      while (startPos < lowerText.length) {
        const idx = lowerText.indexOf(lowerQuery, startPos);
        if (idx === -1) break;

        matches.push({
          messageId: message.id,
          messageIndex,
          blockIndex: block.blockIndex,
          startOffset: idx,
          length: query.length,
        });

        startPos = idx + lowerQuery.length;
      }
    }
  });

  return matches;
};
