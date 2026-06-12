/**
 * Performance benchmarks for entity mention rendering paths.
 *
 * Measures the overhead introduced by entity mention scanning compared to
 * a baseline with no scanning at all (pre-feature behavior).
 *
 * Run with: npx vitest bench src/components/__tests__/entityMentionRendering.bench.ts
 *
 * Three variants are compared for each path:
 * - "no processing": simulates pre-feature behavior (passthrough)
 * - "regex scan": runs the regex on every text node
 * - "fast check + regex": skips regex when "+[" is absent (shipped optimization)
 */

import { bench, describe } from "vitest";

const ENTITY_MENTION_RE = /\+\[([^:]+):([^|]+)\|([^\]]+)\]/g;
const ENTITY_MENTION_FAST_CHECK = "+[";

// --- Test data generators ---

const generateParagraph = (wordCount: number): string => {
  const words = "the quick brown fox jumps over the lazy dog and runs across the field".split(" ");
  const result: Array<string> = [];
  for (let i = 0; i < wordCount; i++) {
    result.push(words[i % words.length]);
  }
  return result.join(" ");
};

const generateDocument = (paragraphCount: number, wordsPerParagraph: number): Array<string> => {
  const paragraphs: Array<string> = [];
  for (let i = 0; i < paragraphCount; i++) {
    paragraphs.push(generateParagraph(wordsPerParagraph));
  }
  return paragraphs;
};

const generateDocumentWithMentions = (
  paragraphCount: number,
  wordsPerParagraph: number,
  mentionsPerParagraph: number,
): Array<string> => {
  const paragraphs: Array<string> = [];
  for (let i = 0; i < paragraphCount; i++) {
    let text = generateParagraph(wordsPerParagraph);
    for (let j = 0; j < mentionsPerParagraph; j++) {
      text += ` +[workspace:ws-${i}-${j}|Workspace ${i}-${j}]`;
    }
    paragraphs.push(text);
  }
  return paragraphs;
};

// --- AlphaMarkdownBlock path simulation ---
//
// In the real code, renderEntityMentions is called inside each component
// override (p, li, h1-h6, etc.). It receives React children and calls
// Children.map, checking each string child. The benchmark simulates this
// by iterating over an array of paragraph strings.

/** Pre-feature baseline: just pass children through, check typeof. */
const markdownNoProcessing = (paragraphs: ReadonlyArray<string>): number => {
  let count = 0;
  for (const child of paragraphs) {
    if (typeof child !== "string") continue;
    // This is what the override did before: return child unchanged
    count += child.length;
  }
  return count;
};

/** Current code without fast-check: run regex on every string child. */
const markdownRegexScan = (paragraphs: ReadonlyArray<string>): number => {
  let totalMatches = 0;
  for (const child of paragraphs) {
    if (typeof child !== "string") continue;
    const regex = new RegExp(ENTITY_MENTION_RE.source, "g");
    while (regex.exec(child) !== null) {
      totalMatches++;
    }
  }
  return totalMatches;
};

/** Shipped code: fast-check before regex. */
const markdownFastCheckThenRegex = (paragraphs: ReadonlyArray<string>): number => {
  let totalMatches = 0;
  for (const child of paragraphs) {
    if (typeof child !== "string") continue;
    if (!child.includes(ENTITY_MENTION_FAST_CHECK)) continue;
    const regex = new RegExp(ENTITY_MENTION_RE.source, "g");
    while (regex.exec(child) !== null) {
      totalMatches++;
    }
  }
  return totalMatches;
};

// --- TipTapViewer path simulation ---
//
// The real code uses doc.descendants() to walk all ProseMirror nodes.
// For text nodes it runs a regex and replaces matches with EntityMention
// nodes via a transaction. The benchmark simulates the traversal + regex
// cost without the actual ProseMirror overhead.

type TextNode = { text: string; pos: number };

const buildTextNodes = (paragraphs: ReadonlyArray<string>): Array<TextNode> => {
  const nodes: Array<TextNode> = [];
  let pos = 0;
  for (const text of paragraphs) {
    nodes.push({ text, pos });
    pos += text.length + 1;
  }
  return nodes;
};

/** Pre-feature baseline: no useEffect, no doc traversal at all. */
const tiptapNoProcessing = (nodes: ReadonlyArray<TextNode>): number => {
  // The editor just renders. No scanning happens.
  return nodes.length;
};

/** Current code without fast-check: traverse + regex every text node. */
const tiptapDocScan = (nodes: ReadonlyArray<TextNode>): number => {
  let totalReplacements = 0;
  for (const node of nodes) {
    if (!node.text) continue;
    const regex = new RegExp(ENTITY_MENTION_RE.source, "g");
    while (regex.exec(node.text) !== null) {
      totalReplacements++;
    }
  }
  return totalReplacements;
};

/** Shipped code: content-level fast-check + per-node fast-check. */
const tiptapFastCheckThenDocScan = (contentHasMention: boolean, nodes: ReadonlyArray<TextNode>): number => {
  if (!contentHasMention) return 0;
  let totalReplacements = 0;
  for (const node of nodes) {
    if (!node.text) continue;
    if (!node.text.includes(ENTITY_MENTION_FAST_CHECK)) continue;
    const regex = new RegExp(ENTITY_MENTION_RE.source, "g");
    while (regex.exec(node.text) !== null) {
      totalReplacements++;
    }
  }
  return totalReplacements;
};

// --- Benchmarks ---

describe("AlphaMarkdownBlock: no mentions (typical case)", () => {
  const small = generateDocument(10, 50);
  const medium = generateDocument(100, 100);
  const large = generateDocument(500, 200);

  bench("no processing (pre-feature) - small", () => {
    markdownNoProcessing(small);
  });
  bench("regex scan - small", () => {
    markdownRegexScan(small);
  });
  bench("fast check + regex (shipped) - small", () => {
    markdownFastCheckThenRegex(small);
  });

  bench("no processing (pre-feature) - medium", () => {
    markdownNoProcessing(medium);
  });
  bench("regex scan - medium", () => {
    markdownRegexScan(medium);
  });
  bench("fast check + regex (shipped) - medium", () => {
    markdownFastCheckThenRegex(medium);
  });

  bench("no processing (pre-feature) - large", () => {
    markdownNoProcessing(large);
  });
  bench("regex scan - large", () => {
    markdownRegexScan(large);
  });
  bench("fast check + regex (shipped) - large", () => {
    markdownFastCheckThenRegex(large);
  });
});

describe("AlphaMarkdownBlock: with mentions", () => {
  const sparse = generateDocumentWithMentions(100, 100, 1);
  const dense = generateDocumentWithMentions(100, 50, 5);

  bench("no processing (pre-feature) - sparse", () => {
    markdownNoProcessing(sparse);
  });
  bench("regex scan - sparse (1 mention/paragraph)", () => {
    markdownRegexScan(sparse);
  });
  bench("fast check + regex (shipped) - sparse", () => {
    markdownFastCheckThenRegex(sparse);
  });

  bench("no processing (pre-feature) - dense", () => {
    markdownNoProcessing(dense);
  });
  bench("regex scan - dense (5 mentions/paragraph)", () => {
    markdownRegexScan(dense);
  });
  bench("fast check + regex (shipped) - dense", () => {
    markdownFastCheckThenRegex(dense);
  });
});

describe("TipTapViewer: no mentions (typical case)", () => {
  const smallNodes = buildTextNodes(generateDocument(10, 50));
  const mediumNodes = buildTextNodes(generateDocument(100, 100));
  const largeNodes = buildTextNodes(generateDocument(500, 200));

  bench("no processing (pre-feature) - small", () => {
    tiptapNoProcessing(smallNodes);
  });
  bench("doc scan - small", () => {
    tiptapDocScan(smallNodes);
  });
  bench("fast check + doc scan (shipped) - small", () => {
    tiptapFastCheckThenDocScan(false, smallNodes);
  });

  bench("no processing (pre-feature) - medium", () => {
    tiptapNoProcessing(mediumNodes);
  });
  bench("doc scan - medium", () => {
    tiptapDocScan(mediumNodes);
  });
  bench("fast check + doc scan (shipped) - medium", () => {
    tiptapFastCheckThenDocScan(false, mediumNodes);
  });

  bench("no processing (pre-feature) - large", () => {
    tiptapNoProcessing(largeNodes);
  });
  bench("doc scan - large", () => {
    tiptapDocScan(largeNodes);
  });
  bench("fast check + doc scan (shipped) - large", () => {
    tiptapFastCheckThenDocScan(false, largeNodes);
  });
});

describe("TipTapViewer: with mentions", () => {
  const sparseNodes = buildTextNodes(generateDocumentWithMentions(100, 100, 1));
  const denseNodes = buildTextNodes(generateDocumentWithMentions(100, 50, 5));

  bench("no processing (pre-feature) - sparse", () => {
    tiptapNoProcessing(sparseNodes);
  });
  bench("doc scan - sparse (1 mention/node)", () => {
    tiptapDocScan(sparseNodes);
  });
  bench("fast check + doc scan (shipped) - sparse", () => {
    tiptapFastCheckThenDocScan(true, sparseNodes);
  });

  bench("no processing (pre-feature) - dense", () => {
    tiptapNoProcessing(denseNodes);
  });
  bench("doc scan - dense (5 mentions/node)", () => {
    tiptapDocScan(denseNodes);
  });
  bench("fast check + doc scan (shipped) - dense", () => {
    tiptapFastCheckThenDocScan(true, denseNodes);
  });
});
