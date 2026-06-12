import type { Element, Root, RootContent } from "hast";
import { describe, expect, it } from "vitest";

import { rehypeCursor } from "./rehypeCursor.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const text = (value: string): { type: "text"; value: string } => ({ type: "text", value });

const el = (
  tagName: string,
  children: Array<Element["children"][number]> = [],
  properties: Element["properties"] = {},
): Element => ({
  type: "element",
  tagName,
  properties,
  children,
});

const root = (...children: Array<Element>): Root => ({ type: "root", children });

const run = (tree: Root): Root => {
  rehypeCursor({ enabled: true })(tree);
  return tree;
};

const hasCursor = (node: Element): boolean =>
  node.children.some((c) => c.type === "element" && c.tagName === "streaming-cursor");

const findCursor = (tree: Root): Element | null => {
  const walk = (children: Array<RootContent | Element["children"][number]>): Element | null => {
    for (const child of children) {
      if (child.type === "element") {
        if (child.tagName === "streaming-cursor") return child;
        const found = walk(child.children);
        if (found) return found;
      }
    }
    return null;
  };
  return walk(tree.children);
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("rehypeCursor", () => {
  it("no-ops when disabled", () => {
    const tree = root(el("p", [text("Hello")]));
    rehypeCursor({ enabled: false })(tree);
    expect(findCursor(tree)).toBeNull();
  });

  it("appends cursor to a paragraph", () => {
    const p = el("p", [text("Hello")]);
    run(root(p));
    expect(hasCursor(p)).toBe(true);
  });

  it("appends cursor to the last paragraph only", () => {
    const p1 = el("p", [text("First")]);
    const p2 = el("p", [text("Second")]);
    run(root(p1, p2));
    expect(hasCursor(p1)).toBe(false);
    expect(hasCursor(p2)).toBe(true);
  });

  it.each(["h1", "h2", "h3", "h4", "h5", "h6"])("appends cursor to <%s>", (tag) => {
    const heading = el(tag, [text("Title")]);
    run(root(heading));
    expect(hasCursor(heading)).toBe(true);
  });

  it("appends cursor to last <li> in <ul>", () => {
    const li1 = el("li", [text("A")]);
    const li2 = el("li", [text("B")]);
    const ul = el("ul", [li1, li2]);
    run(root(ul));
    expect(hasCursor(li1)).toBe(false);
    expect(hasCursor(li2)).toBe(true);
  });

  it("appends cursor to last <li> in <ol>", () => {
    const li1 = el("li", [text("1")]);
    const li2 = el("li", [text("2")]);
    const ol = el("ol", [li1, li2]);
    run(root(ol));
    expect(hasCursor(li2)).toBe(true);
  });

  it("recurses into blockquote", () => {
    const p = el("p", [text("Quoted")]);
    const bq = el("blockquote", [p]);
    run(root(bq));
    expect(hasCursor(p)).toBe(true);
  });

  it("recurses into nested blockquotes", () => {
    const innerP = el("p", [text("Inner")]);
    const innerBq = el("blockquote", [innerP]);
    const outerBq = el("blockquote", [el("p", [text("Outer")]), innerBq]);
    run(root(outerBq));
    expect(hasCursor(innerP)).toBe(true);
  });

  it("appends cursor to last table cell", () => {
    const td1 = el("td", [text("A")]);
    const td2 = el("td", [text("B")]);
    const tr = el("tr", [td1, td2]);
    const tbody = el("tbody", [tr]);
    const table = el("table", [tbody]);
    run(root(table));
    expect(hasCursor(td2)).toBe(true);
    expect(hasCursor(td1)).toBe(false);
  });

  it("falls back to root for <pre>", () => {
    const code = el("code", [text("x = 1\n")]);
    const pre = el("pre", [code]);
    const tree = root(pre);
    run(tree);
    expect(hasCursor(code)).toBe(false);
    // Cursor should be appended at root level
    const last = tree.children[tree.children.length - 1] as Element;
    expect(last.tagName).toBe("streaming-cursor");
  });

  it("falls back to root for <hr>", () => {
    const tree = root(el("p", [text("Before")]), el("hr"));
    run(tree);
    // Cursor should be at root, not inside <hr> or the earlier <p>
    const last = tree.children[tree.children.length - 1] as Element;
    expect(last.tagName).toBe("streaming-cursor");
  });

  it("appends to root when tree has no element children", () => {
    const tree: Root = { type: "root", children: [text("raw text")] };
    run(tree);
    const last = tree.children[tree.children.length - 1];
    expect(last.type === "element" && last.tagName === "streaming-cursor").toBe(true);
  });

  it("appends to root when tree is empty", () => {
    const tree: Root = { type: "root", children: [] };
    run(tree);
    expect(tree.children).toHaveLength(1);
    const cursor = tree.children[0] as Element;
    expect(cursor.tagName).toBe("streaming-cursor");
  });
});
