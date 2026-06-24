import { Extension } from "@tiptap/core";
import type { EditorState, Transaction } from "@tiptap/pm/state";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";

/**
 * Trigger characters that open a suggestion popover. The dismissal plugin
 * tracks positions in the doc that hold one of these characters.
 *
 * Kept in sync with the `char` fields on `createMentionPickerSuggestion`,
 * `createSkillSuggestion`, and `createFileSuggestion` (`+`, `@`, `/`).
 */
export const SUGGESTION_TRIGGER_CHARS: ReadonlySet<string> = new Set(["+", "@", "/"]);

type DismissalState = {
  /**
   * Document positions that hold a trigger character whose suggestion
   * popover the user has explicitly dismissed (Escape, click-away, or
   * cursor-away). The `allow()` callback of each suggestion config
   * returns false when the match's `range.from` is in this set, which
   * keeps the popover closed even though the regex still finds a match.
   */
  readonly dismissed: ReadonlySet<number>;
};

type DismissalMeta = { type: "dismiss"; pos: number };

export const suggestionDismissalKey = new PluginKey<DismissalState>("suggestionDismissal");

/**
 * Dispatch a transaction that records the trigger position as dismissed.
 * Called from `closePopover()` in SuggestionUtils whenever a popover is
 * torn down — Escape, click-outside, cursor-away (regex no longer matches),
 * or after an item is committed. In the commit case, the trigger char
 * gets replaced by a chip node, and the next `apply()` prunes the entry
 * because the char at that position is no longer a trigger.
 */
export const dismissTrigger = (view: EditorView, pos: number): void => {
  const meta: DismissalMeta = { type: "dismiss", pos };
  view.dispatch(view.state.tr.setMeta(suggestionDismissalKey, meta));
};

export const isPositionDismissed = (state: EditorState, pos: number): boolean => {
  const pluginState = suggestionDismissalKey.getState(state);
  return pluginState ? pluginState.dismissed.has(pos) : false;
};

const charAtPos = (doc: EditorState["doc"], pos: number): string | null => {
  if (pos < 0 || pos >= doc.content.size) return null;
  const $pos = doc.resolve(pos);
  if ($pos.parentOffset >= $pos.parent.content.size) return null;
  return $pos.parent.textBetween($pos.parentOffset, $pos.parentOffset + 1, "\0", "\0");
};

/**
 * Content of the textblock from `pos + 1` to its end. Used to detect
 * whether the user has typed/deleted within the dismissed trigger's
 * "query area" — if this content changed across a transaction, the
 * dismissal is invalidated because the user is composing again.
 */
const afterTriggerContent = (doc: EditorState["doc"], pos: number): string | null => {
  if (pos < 0 || pos >= doc.content.size) return null;
  const $pos = doc.resolve(pos);
  const blockStart = pos - $pos.parentOffset;
  const blockEnd = blockStart + $pos.parent.content.size;
  if (pos + 1 > blockEnd) return "";
  return doc.textBetween(pos + 1, blockEnd, "\0", "\0");
};

const applyTransaction = (tr: Transaction, prev: DismissalState): DismissalState => {
  const meta = tr.getMeta(suggestionDismissalKey) as DismissalMeta | undefined;

  let next = prev.dismissed;

  if (tr.docChanged && next.size > 0) {
    const mapped = new Set<number>();
    for (const oldPos of next) {
      // Bias to "after" so the position follows the trigger character
      // when text is inserted exactly at the trigger's position
      // (insertion BEFORE the trigger pushes the trigger forward).
      // For insertions strictly after, the bias is moot.
      // For deletions/replacements that wipe out the trigger, the
      // mapped position lands at the splice point and the trigger-char
      // check below catches it.
      const newPos = tr.mapping.map(oldPos, 1);

      // Drop if the trigger char is gone (deleted, replaced by a chip,
      // or the textblock vanished entirely).
      const newChar = charAtPos(tr.doc, newPos);
      if (newChar === null || !SUGGESTION_TRIGGER_CHARS.has(newChar)) continue;

      // Drop if the user edited content within the trigger's textblock
      // at-or-after the trigger — that's "I'm composing this mention
      // again" and the popover should reopen. Compare the post-trigger
      // textblock content before vs after.
      const oldAfter = afterTriggerContent(tr.before, oldPos);
      const newAfter = afterTriggerContent(tr.doc, newPos);
      if (oldAfter !== newAfter) continue;

      mapped.add(newPos);
    }
    next = mapped;
  }

  if (meta?.type === "dismiss") {
    if (!next.has(meta.pos)) {
      const updated = new Set(next);
      updated.add(meta.pos);
      next = updated;
    }
  }

  return next === prev.dismissed ? prev : { dismissed: next };
};

const suggestionDismissalPlugin = (): Plugin<DismissalState> =>
  new Plugin<DismissalState>({
    key: suggestionDismissalKey,
    state: {
      init: (): DismissalState => ({ dismissed: new Set() }),
      apply: applyTransaction,
    },
  });

/**
 * TipTap wrapper around the dismissal plugin. Register once in the
 * editor's extensions list — every suggestion's `allow()` callback can
 * then call `isPositionDismissed(state, range.from)` to suppress the
 * popover at known-dismissed trigger positions.
 */
export const SuggestionDismissalExtension = Extension.create({
  name: "suggestionDismissal",
  addProseMirrorPlugins() {
    return [suggestionDismissalPlugin()];
  },
});
