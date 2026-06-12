/**
 * Remark plugin that preserves the original marker number of each ordered-list
 * item by reading it back out of the source markdown.
 *
 * CommonMark — and therefore remark-gfm — drops per-item markers and
 * re-numbers items sequentially starting from the first marker (the list's
 * ``start``). For a user who typed
 *
 *     3. A
 *
 *     17. B
 *
 *     20. C
 *
 * the rendered list would otherwise show 3, 4, 5. We want 3, 17, 20.
 *
 * Each ``listItem`` node still carries a ``position.start.offset`` into the
 * original source string, so the original marker (a run of digits at that
 * offset) can be recovered after parsing. Setting ``data.hProperties.value``
 * propagates through ``mdast-util-to-hast`` and ends up as the HTML
 * ``value=`` attribute on the ``<li>`` — which the browser honours when
 * computing list-item numbering.
 *
 * Emitting ``value=`` on every item, including in sequential lists, is a
 * no-op for the rendered numbering.
 */
import type { List, Root } from "mdast";
import { visit } from "unist-util-visit";

export const remarkPreserveOrderedListMarkers =
  () =>
  (tree: Root, file: { value?: string | Uint8Array }): void => {
    const source = typeof file.value === "string" ? file.value : "";
    if (!source) return;

    visit(tree, "list", (node: List) => {
      if (!node.ordered) return;
      for (const item of node.children) {
        const offset = item.position?.start.offset;
        if (offset === undefined) continue;

        // The marker is the leading run of digits at the item's start position.
        // CommonMark also allows the ``)`` form (``1) foo``) — accept either.
        // Cap the scan length so a pathologically long line can't blow up.
        const marker = source.slice(offset, offset + 24).match(/^[ \t]*(\d+)[.)]/);
        if (!marker) continue;

        const value = Number(marker[1]);
        if (!Number.isFinite(value)) continue;

        const data = (item.data ??= {});
        const hProps = (data.hProperties ??= {}) as Record<string, unknown>;
        hProps.value = value;
      }
    });
  };
