/**
 * Rehype plugin that appends a `<streaming-cursor />` element to the last
 * inline-content node in the markdown tree. ReactMarkdown renders this custom
 * tag via the `components` map, so the cursor becomes a normal React component
 * — no imperative DOM manipulation needed.
 */
import type { Element, ElementContent, Root, RootContent } from "hast";

const INLINE_TAGS = new Set(["p", "h1", "h2", "h3", "h4", "h5", "h6"]);

const cursorNode = (): Element => ({
  type: "element",
  tagName: "streaming-cursor",
  properties: {},
  children: [],
});

/** Find the deepest last element that holds inline text content. */
const findCursorTarget = (children: Array<RootContent | ElementContent>): Element | undefined => {
  for (let i = children.length - 1; i >= 0; i--) {
    const node = children[i];
    if (node.type !== "element") continue;

    if (INLINE_TAGS.has(node.tagName)) return node;

    if (node.tagName === "ul" || node.tagName === "ol") {
      return [...node.children].reverse().find((c): c is Element => c.type === "element" && c.tagName === "li");
    }

    if (node.tagName === "blockquote") {
      return findCursorTarget(node.children);
    }

    // <pre><code>...</code></pre> is replaced by AlphaCodeBlock via the
    // components map — injecting into <code> would break its children.
    // Fall through to append at root level instead.
    if (node.tagName === "pre") return undefined;

    if (node.tagName === "table") {
      return findLastTableCell(node);
    }

    // HR is void — no inline content to append into.
    if (node.tagName === "hr") return undefined;

    return node;
  }
  return undefined;
};

const findLastTableCell = (table: Element): Element | undefined => {
  const tbody = table.children.find((c): c is Element => c.type === "element" && c.tagName === "tbody");
  const container = tbody ?? table;
  const rows = container.children.filter((c): c is Element => c.type === "element" && c.tagName === "tr");
  const lastRow = rows[rows.length - 1];
  if (!lastRow) return undefined;
  const cells = lastRow.children.filter(
    (c): c is Element => c.type === "element" && (c.tagName === "td" || c.tagName === "th"),
  );
  return cells[cells.length - 1];
};

export type RehypeCursorOptions = {
  enabled: boolean;
};

export const rehypeCursor = (options: RehypeCursorOptions): ((tree: Root) => void) => {
  return (tree) => {
    if (!options.enabled) return;

    const target = findCursorTarget(tree.children);
    if (target) {
      target.children.push(cursorNode());
    } else {
      // Fallback: append directly to the root (e.g. after an <hr>).
      tree.children.push(cursorNode());
    }
  };
};
