import type { Editor as TipTapEditor } from "@tiptap/core";
import { Editor } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { TextSelection } from "@tiptap/pm/state";
import { afterEach, describe, expect, it } from "vitest";

import {
  dismissTrigger,
  isPositionDismissed,
  SUGGESTION_TRIGGER_CHARS,
  SuggestionDismissalExtension,
  suggestionDismissalKey,
} from "./suggestionDismissalPlugin";

/**
 * A minimal TipTap editor wired with just enough to exercise the
 * dismissal plugin: Document/Paragraph/Text plus the dismissal extension
 * itself. Using a real editor (not a mock) so position-mapping through
 * transactions is exercised as it would be in production.
 */
const createEditor = (content?: string): TipTapEditor =>
  new Editor({
    extensions: [Document, Paragraph, Text, SuggestionDismissalExtension],
    content,
  });

const dismissedSet = (editor: TipTapEditor): ReadonlySet<number> => {
  const state = suggestionDismissalKey.getState(editor.state);
  if (!state) throw new Error("dismissal plugin state missing");
  return state.dismissed;
};

const setSelection = (editor: TipTapEditor, pos: number): void => {
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, pos)));
};

const insertAt = (editor: TipTapEditor, pos: number, text: string): void => {
  editor.view.dispatch(editor.state.tr.insertText(text, pos));
};

const deleteRange = (editor: TipTapEditor, from: number, to: number): void => {
  editor.view.dispatch(editor.state.tr.delete(from, to));
};

let editors: Array<TipTapEditor> = [];
const trackedEditor = (content?: string): TipTapEditor => {
  const e = createEditor(content);
  editors.push(e);
  return e;
};

afterEach(() => {
  for (const e of editors) e.destroy();
  editors = [];
});

describe("SUGGESTION_TRIGGER_CHARS", () => {
  it("includes the three trigger characters used by suggestion configs", () => {
    expect(SUGGESTION_TRIGGER_CHARS.has("+")).toBe(true);
    expect(SUGGESTION_TRIGGER_CHARS.has("@")).toBe(true);
    expect(SUGGESTION_TRIGGER_CHARS.has("/")).toBe(true);
  });

  it("does not include unrelated punctuation", () => {
    expect(SUGGESTION_TRIGGER_CHARS.has("#")).toBe(false);
    expect(SUGGESTION_TRIGGER_CHARS.has(" ")).toBe(false);
    expect(SUGGESTION_TRIGGER_CHARS.has("a")).toBe(false);
    expect(SUGGESTION_TRIGGER_CHARS.has("%")).toBe(false);
  });
});

describe("dismissal plugin: initial state", () => {
  it("starts with an empty dismissed set", () => {
    const editor = trackedEditor("<p>hello</p>");
    expect(dismissedSet(editor).size).toBe(0);
  });

  it("isPositionDismissed returns false for any position", () => {
    const editor = trackedEditor("<p>+ hello</p>");
    for (let pos = 0; pos <= editor.state.doc.content.size; pos++) {
      expect(isPositionDismissed(editor.state, pos)).toBe(false);
    }
  });
});

describe("dismissTrigger", () => {
  it("records the trigger position as dismissed", () => {
    const editor = trackedEditor("<p>+ hello</p>");
    dismissTrigger(editor.view, 1);
    expect(dismissedSet(editor).has(1)).toBe(true);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
  });

  it("is idempotent — dismissing the same position twice keeps a single entry", () => {
    const editor = trackedEditor("<p>+ hello</p>");
    dismissTrigger(editor.view, 1);
    dismissTrigger(editor.view, 1);
    expect(dismissedSet(editor).size).toBe(1);
  });

  it("supports multiple distinct dismissed positions", () => {
    const editor = trackedEditor("<p>+ a @ b / c</p>");
    dismissTrigger(editor.view, 1); // +
    dismissTrigger(editor.view, 5); // @
    dismissTrigger(editor.view, 9); // /
    const set = dismissedSet(editor);
    expect(set.size).toBe(3);
    expect(set.has(1)).toBe(true);
    expect(set.has(5)).toBe(true);
    expect(set.has(9)).toBe(true);
  });

  it("does not affect other positions", () => {
    const editor = trackedEditor("<p>+ a @ b</p>");
    dismissTrigger(editor.view, 1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
    expect(isPositionDismissed(editor.state, 5)).toBe(false);
  });
});

describe("selection-only transactions", () => {
  it("preserve dismissed entries", () => {
    // The whole point of the plugin: cursor moves don't reopen the popover.
    const editor = trackedEditor("<p>+ hello world</p>");
    dismissTrigger(editor.view, 1);
    setSelection(editor, 1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
    setSelection(editor, 5);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
    setSelection(editor, 1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
  });
});

describe("dismissal pruning: trigger char missing", () => {
  it("drops the entry when the trigger char is deleted", () => {
    const editor = trackedEditor("<p>+ hello</p>");
    dismissTrigger(editor.view, 1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
    deleteRange(editor, 1, 2);
    expect(dismissedSet(editor).size).toBe(0);
  });

  it("drops the entry when the trigger char is replaced with non-trigger text", () => {
    const editor = trackedEditor("<p>+ hello</p>");
    dismissTrigger(editor.view, 1);
    editor.view.dispatch(editor.state.tr.replaceWith(1, 2, editor.state.schema.text("x")));
    expect(dismissedSet(editor).size).toBe(0);
  });

  it("drops the entry when the entire textblock is deleted", () => {
    const editor = trackedEditor("<p>before</p><p>+ trigger</p>");
    // Trigger '+' lives in the second paragraph: positions are
    //   0 <p>            6 </p> 7 <p>             16 </p>
    //   1 b 2 e 3 f 4 o 5 r 6 e        8 + 9 sp 10 t...
    dismissTrigger(editor.view, 8);
    expect(isPositionDismissed(editor.state, 8)).toBe(true);
    deleteRange(editor, 7, 17);
    expect(dismissedSet(editor).size).toBe(0);
  });
});

describe("dismissal pruning: edits after the trigger", () => {
  it("drops the entry when the user types right after the trigger (composing query)", () => {
    const editor = trackedEditor("<p>+</p>");
    dismissTrigger(editor.view, 1);
    insertAt(editor, 2, "h");
    expect(dismissedSet(editor).size).toBe(0);
  });

  it("drops the entry when the user types in the trigger's textblock anywhere after the trigger", () => {
    const editor = trackedEditor("<p>+ hello</p>");
    dismissTrigger(editor.view, 1);
    // Type at the very end of the textblock — content after the trigger
    // changed, so the dismissal must not stick.
    insertAt(editor, 7, "!");
    expect(dismissedSet(editor).size).toBe(0);
  });

  it("drops the entry when the user deletes content right after the trigger", () => {
    const editor = trackedEditor("<p>+ hello</p>");
    dismissTrigger(editor.view, 1);
    deleteRange(editor, 2, 3);
    expect(dismissedSet(editor).size).toBe(0);
  });
});

describe("dismissal pruning: edits before the trigger preserve dismissal", () => {
  it("preserves dismissal when text is inserted before the trigger in the same textblock", () => {
    // The position should be remapped forward but the dismissal kept,
    // because the post-trigger content is unchanged.
    const editor = trackedEditor("<p>+ hello</p>");
    dismissTrigger(editor.view, 1);
    insertAt(editor, 1, "abc");
    // '+' has moved from pos 1 to pos 4. Dismissal follows.
    const set = dismissedSet(editor);
    expect(set.size).toBe(1);
    expect(set.has(4)).toBe(true);
    expect(isPositionDismissed(editor.state, 4)).toBe(true);
  });

  it("preserves dismissal when text is inserted before the trigger in a different paragraph", () => {
    const editor = trackedEditor("<p>first</p><p>+ trigger</p>");
    // '+' is in second paragraph at position 8 (see earlier comment for indices).
    dismissTrigger(editor.view, 8);
    insertAt(editor, 1, "PREFIX");
    // '+' shifts forward by 6.
    const set = dismissedSet(editor);
    expect(set.size).toBe(1);
    expect(set.has(14)).toBe(true);
  });

  it("preserves dismissal when content in a SEPARATE textblock changes", () => {
    const editor = trackedEditor("<p>+ trigger</p><p>other</p>");
    dismissTrigger(editor.view, 1);
    // Edit the second paragraph; the trigger's textblock is untouched.
    insertAt(editor, 13, "x");
    expect(dismissedSet(editor).size).toBe(1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
  });
});

describe("dismissal pruning: partial — only invalidated entries drop", () => {
  it("invalidates the trigger whose textblock was edited and keeps the others", () => {
    const editor = trackedEditor("<p>+ a</p><p>+ b</p><p>+ c</p>");
    // Trigger positions: 1, 6, 11.
    dismissTrigger(editor.view, 1);
    dismissTrigger(editor.view, 6);
    dismissTrigger(editor.view, 11);
    expect(dismissedSet(editor).size).toBe(3);
    // Edit the second paragraph after the trigger: only that one drops.
    insertAt(editor, 8, "!");
    const set = dismissedSet(editor);
    expect(set.size).toBe(2);
    expect(set.has(1)).toBe(true);
    expect(set.has(6)).toBe(false);
    // Pos 11 shifted forward by 1 to pos 12.
    expect(set.has(12)).toBe(true);
  });
});

describe("position remapping", () => {
  it("remaps positions through a deletion before the trigger", () => {
    const editor = trackedEditor("<p>abc+ x</p>");
    // '+' is at pos 4.
    dismissTrigger(editor.view, 4);
    deleteRange(editor, 1, 4); // delete "abc"
    // '+' is now at pos 1; dismissal should follow.
    const set = dismissedSet(editor);
    expect(set.size).toBe(1);
    expect(set.has(1)).toBe(true);
  });

  it("survives a series of edits that all preserve the trigger and its query area", () => {
    // Realistic scenario: user dismisses, then types lots of unrelated
    // text in another paragraph, then comes back near the trigger.
    const editor = trackedEditor("<p>+ a</p><p>second</p>");
    dismissTrigger(editor.view, 1);
    insertAt(editor, 12, "more text"); // edit second paragraph
    insertAt(editor, 21, " and more");
    expect(dismissedSet(editor).has(1)).toBe(true);
  });
});

describe("combined doc change + dismiss meta in a single transaction", () => {
  it("applies the doc-change pruning AND the new dismiss in one transaction", () => {
    const editor = trackedEditor("<p>+ a</p><p>+ b</p>");
    // Prime: dismiss the second '+'.
    dismissTrigger(editor.view, 6);
    expect(dismissedSet(editor).has(6)).toBe(true);
    // Single tr that both (a) edits the second paragraph (invalidating
    // the dismissal at pos 6) and (b) dismisses the first '+' at pos 1.
    const tr = editor.state.tr.insertText("!", 8).setMeta(suggestionDismissalKey, { type: "dismiss", pos: 1 });
    editor.view.dispatch(tr);
    const set = dismissedSet(editor);
    expect(set.has(1)).toBe(true);
    expect(set.has(6)).toBe(false);
    expect(set.size).toBe(1);
  });
});

describe("trigger characters", () => {
  it.each([
    ["+", "+"],
    ["@", "@"],
    ["/", "/"],
  ])("recognizes %s as a valid trigger", (_label, char) => {
    const editor = trackedEditor(`<p>${char} hi</p>`);
    dismissTrigger(editor.view, 1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
    // Deleting the trigger should drop the entry.
    deleteRange(editor, 1, 2);
    expect(dismissedSet(editor).size).toBe(0);
  });

  it("drops dismissals for non-trigger characters on the next doc change", () => {
    // If something dispatches a stale dismissal (e.g. a position that
    // has since been overwritten by a chip insertion), the next
    // doc-changing transaction prunes it. This is the safety net for
    // the post-insertion path where closePopover() fires after the
    // trigger char has already been replaced.
    const editor = trackedEditor("<p>x hi</p>");
    dismissTrigger(editor.view, 1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
    // Any doc change triggers the prune pass.
    insertAt(editor, 5, "!");
    expect(dismissedSet(editor).size).toBe(0);
  });
});

describe("end-of-textblock edge cases", () => {
  it("recognizes a trigger at the last position of the textblock", () => {
    const editor = trackedEditor("<p>hi +</p>");
    // '+' at position 4.
    dismissTrigger(editor.view, 4);
    expect(isPositionDismissed(editor.state, 4)).toBe(true);
  });

  it("drops the entry when the user types right after a trailing-trigger", () => {
    const editor = trackedEditor("<p>hi +</p>");
    dismissTrigger(editor.view, 4);
    insertAt(editor, 5, "x");
    expect(dismissedSet(editor).size).toBe(0);
  });

  it("isPositionDismissed handles out-of-bounds positions safely", () => {
    const editor = trackedEditor("<p>hi</p>");
    expect(isPositionDismissed(editor.state, -1)).toBe(false);
    expect(isPositionDismissed(editor.state, 999)).toBe(false);
  });
});

describe("integration: simulated user flows", () => {
  it("reproduces the original bug — type +, dismiss, cursor back: stays dismissed", () => {
    // Mirrors the production lifecycle: user types '+', the popover opens,
    // user types space which causes the suggestion plugin to fire onExit,
    // closePopover dispatches dismissTrigger at the '+' position.
    const editor = trackedEditor("<p>+ rest</p>");
    // Simulate the closePopover dispatch.
    dismissTrigger(editor.view, 1);
    // Cursor moves around — emulating the user clicking back into the line.
    setSelection(editor, 4);
    setSelection(editor, 1);
    setSelection(editor, 2);
    // The dismissal must survive every cursor move.
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
  });

  it("after dismissal, typing right after the trigger reopens (drops the entry)", () => {
    const editor = trackedEditor("<p>+</p>");
    dismissTrigger(editor.view, 1);
    expect(isPositionDismissed(editor.state, 1)).toBe(true);
    // User goes back and starts typing the query.
    insertAt(editor, 2, "f");
    expect(isPositionDismissed(editor.state, 1)).toBe(false);
  });

  it("dismissing one trigger does not affect a fresh trigger at a different position", () => {
    const editor = trackedEditor("<p>+ a, then later</p>");
    dismissTrigger(editor.view, 1);
    // User types a fresh '@' at the end of the line.
    insertAt(editor, 16, "@");
    // The original + dismissal: same textblock as the new '@', and the
    // edit happened well after pos 1, so it gets pruned.
    expect(isPositionDismissed(editor.state, 1)).toBe(false);
    // The new '@' was never dismissed.
    expect(isPositionDismissed(editor.state, 16)).toBe(false);
  });

  it("dismissing in paragraph A doesn't get cleared by typing in paragraph B", () => {
    const editor = trackedEditor("<p>+ a</p><p>+ b</p>");
    dismissTrigger(editor.view, 1);
    dismissTrigger(editor.view, 6);
    // Type in second paragraph, after the trigger. The first paragraph's
    // dismissal must not be affected.
    insertAt(editor, 8, "z");
    const set = dismissedSet(editor);
    expect(set.has(1)).toBe(true);
    expect(set.has(6)).toBe(false);
  });
});
