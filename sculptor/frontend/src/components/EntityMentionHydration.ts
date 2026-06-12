import type { Editor } from "@tiptap/react";

// Markdown serialization for entity-mention chips, produced by
// `renderMarkdown` in TipTapConfig. The TipTap markdown parser doesn't know
// about this token, so any time we load markdown that contains it (a draft
// restored from localStorage, a sent message rendered in TipTapViewer) the
// token survives as literal text in the document until we walk it ourselves.
const ENTITY_MENTION_RE = /\+\[([^:]+):([^|]+)\|([^\]]+)\]/g;

/**
 * Scan the editor document for `+[type:id|display_name]` text and replace
 * each match with an entity-mention node (the unified `mention` node in its
 * entity variant). Idempotent — already-hydrated mention nodes are not text
 * nodes, so they are skipped.
 *
 * Text inside code blocks or carrying an inline `code` mark is preserved
 * verbatim — code spans must always round-trip without being re-parsed as
 * chips, so the user can quote a literal `+[type:id|name]` token.
 *
 * Call this after every `setContent({ contentType: "markdown" })` that may
 * carry entity-mention markdown — both the editable composer and the
 * read-only viewer need it, since TipTap's markdown parser leaves the
 * compact `+[…]` token as literal text.
 */
export const hydrateEntityMentions = (editor: Editor): void => {
  const { doc, tr, schema } = editor.state;
  const codeMark = schema.marks.code;

  const replacements: Array<{
    from: number;
    to: number;
    entityType: string;
    entityId: string;
    entityDisplayName: string;
  }> = [];

  doc.descendants((node, pos, parent) => {
    if (!node.isText || !node.text) return;
    if (!node.text.includes("+[")) return;
    // Skip text inside a code block — the parent text-block carries the
    // codeBlock node type. Skip text with the inline `code` mark too, so
    // `` `+[…]` `` round-trips as a literal code span.
    if (parent && parent.type.name === "codeBlock") return;
    if (codeMark && codeMark.isInSet(node.marks)) return;

    const regex = new RegExp(ENTITY_MENTION_RE.source, "g");
    let match: RegExpExecArray | null;
    while ((match = regex.exec(node.text)) !== null) {
      replacements.push({
        from: pos + match.index,
        to: pos + match.index + match[0].length,
        entityType: match[1],
        entityId: match[2],
        entityDisplayName: match[3],
      });
    }
  });

  if (replacements.length === 0) return;

  // Apply in descending `from` order so earlier offsets stay valid as
  // later ranges are spliced out of the same transaction. Within one text
  // node `regex.exec` already produced ascending matches; across text
  // nodes (e.g. tokens in successive paragraphs) the same invariant has
  // to hold against the cumulative diff, hence one global sort.
  replacements.sort((a, b) => b.from - a.from);

  for (const r of replacements) {
    const mentionNode = editor.schema.nodes.mention.create({
      entityType: r.entityType,
      entityId: r.entityId,
      entityDisplayName: r.entityDisplayName,
    });
    tr.replaceWith(r.from, r.to, mentionNode);
  }

  editor.view.dispatch(tr);
};
