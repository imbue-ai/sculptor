import { wrappingInputRule } from "@tiptap/core";
import BulletList from "@tiptap/extension-bullet-list";
import Mention from "@tiptap/extension-mention";
import Paragraph from "@tiptap/extension-paragraph";
import Placeholder from "@tiptap/extension-placeholder";
import { Markdown } from "@tiptap/markdown";
import { NodeSelection, TextSelection } from "@tiptap/pm/state";
import { Extension, ReactNodeViewRenderer } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { common, createLowlight } from "lowlight";
import { Marked, type marked as MarkedInstance, type Tokens } from "marked";

import { ElementIds } from "~/api";

import { CustomCodeBlockLowlight } from "./CodeBlockExtension";
import styles from "./Editor.module.scss";
import type { EntityDataRef } from "./EntityMentionSuggestion";
import { MentionNodeView } from "./MentionNodeView";
import { createMentionPickerSuggestion } from "./MentionPickerSuggestion";
import { createSkillSuggestion } from "./SkillSuggestion";
import { SuggestionDismissalExtension } from "./SuggestionDismissalPlugin";
import { createFileSuggestion } from "./SuggestionUtils";

/**
 * The default Paragraph extension serializes empty paragraphs as the HTML entity
 * string "&nbsp;". The marked tokenizer misparses this inside list items, causing
 * the literal text "&nbsp;" to appear after a round-trip.
 *
 * We serialize empty paragraphs as a zero-width space (\u200B) instead. Unlike
 * \u00A0 (NBSP), \u200B does not match /^\s/, so the ordered list tokenizer's
 * INDENTED_LINE_REGEX won't treat it as indented continuation content — which
 * previously caused text after a list to be swallowed. And unlike an empty string,
 * \u200B is real content, so the paragraph survives a round-trip through the
 * markdown parser without collapsing.
 */
const CustomParagraph = Paragraph.extend({
  renderMarkdown: (node, h) => {
    if (!node) {
      return "";
    }
    const content = Array.isArray(node.content) ? node.content : [];
    if (content.length === 0) {
      return "\u200B";
    }
    return h.renderChildren(content);
  },
});

/**
 * Drop `+` from the bullet-list input rule. The default rule wraps the line
 * in a list when the user types `*`, `-`, or `+` followed by a space \u2014 but
 * `+` is also the trigger for our mention prefilter popover, so users who
 * pick a `+` mention and then type a space would unintentionally start a
 * list. `*` and `-` are still honored.
 */
const CustomBulletList = BulletList.extend({
  addInputRules() {
    return [
      wrappingInputRule({
        find: /^\s*([-*])\s$/,
        type: this.type,
      }),
    ];
  },
});

/**
 * Minimal HTML-attribute escape for values we write into the
 * `data-sculptor-node` span during draft serialisation. The string is embedded
 * inside a double-quoted attribute, so at minimum `&` and `"` must be escaped;
 * `<` and `>` are also escaped to keep the serialized span syntactically safe
 * if marked's tokenizer ever re-scans the value. Browsers automatically
 * unescape these on `getAttribute()`.
 */
const escapeHtmlAttr = (value: string): string =>
  value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/**
 * Regex that matches a complete `<span data-sculptor-node>…</span>` element,
 * including any additional data-* attributes (e.g. `data-skill-description`,
 * `data-skill-type`) that carry skill chip metadata.  These spans are emitted
 * by the Mention extension's `renderMarkdown` when serialising mentions to
 * the draft string stored in localStorage.  We need to allow them through
 * marked so the MarkdownManager's `parseHTMLToken` path can convert them
 * back into Mention nodes via the `parseHTML` rule added below.
 */
const SCULPTOR_NODE_SPAN_RE = /^<span\s+data-sculptor-node(?:\s+[^>]*)?>([\s\S]*?)<\/span>/;

/**
 * Custom marked instance that does not treat angle-bracket text (e.g.
 * `<skill-name>`, `<Component />`) as HTML.  Without this, marked's
 * tokenizer interprets any `<word>` as an HTML tag and the
 * MarkdownManager's parseHTMLToken silently drops it.
 *
 * Returning `undefined` tells marked "no match" so the text falls through
 * to the `inlineText` rule and is preserved verbatim.
 *
 * Exception: `<span data-sculptor-node>` tags produced by the Mention
 * extension's `renderMarkdown` are explicitly allowed through so that
 * draft @-mentions survive the round-trip through localStorage.
 */
const sculptorMarked = new Marked({
  tokenizer: {
    html(_src: string): Tokens.HTML | undefined {
      return undefined;
    },
    tag(src: string): Tokens.Tag | undefined {
      // Allow sculptor mention spans through so they reach parseHTMLToken.
      const match = SCULPTOR_NODE_SPAN_RE.exec(src);
      if (match) {
        return {
          type: "html",
          raw: match[0],
          inLink: false,
          inRawBlock: false,
          text: match[0],
          block: false,
        };
      }
      return undefined;
    },
  },
});

const lowlight = createLowlight(common);

type TipTapConfigOptions = {
  placeholder?: string;
  editable?: boolean;
  projectID?: string;
  workspaceID?: string;
  entityDataRef?: EntityDataRef;
  /**
   * Fired when the user picks the "Images" category from the `+` prefilter
   * popover. Hosts wire this to whatever opens their image-attachment
   * dialog (typically the hidden file input owned by `FileUpload`).
   * Omitting it hides the Images category from the prefilter list.
   */
  onTriggerImageUpload?: () => void;
};

/**
 * Creates the shared TipTap extensions configuration used by both Editor and TipTapViewer
 */
export const createTipTapExtensions = ({
  placeholder,
  editable = true,
  projectID,
  workspaceID,
  entityDataRef,
  onTriggerImageUpload,
}: TipTapConfigOptions): Array<Extension> => {
  const extensions = [
    StarterKit.configure({
      codeBlock: false,
      link: false,
      paragraph: false,
      bulletList: false,
    }),
    CustomParagraph as Extension<unknown, unknown>,
    CustomBulletList as Extension<unknown, unknown>,
    // Tracks trigger positions whose suggestion popover the user has
    // dismissed (Escape, click-away, cursor-away). Each suggestion's
    // `allow()` consults this state via `isPositionDismissed` so that
    // moving the cursor back into a previously-dismissed range does
    // not reopen the popover.
    SuggestionDismissalExtension as Extension<unknown, unknown>,
    // `indentation.size: 4` overrides @tiptap/markdown's 2-space default so
    // nested list items in the output of `getMarkdown()` are indented far
    // enough to nest under any list marker, including double-digit ordered
    // markers like `10. `. CommonMark — and therefore remark-gfm, which
    // renders chat messages downstream — only treats content as nested under
    // a `1. ` item when it's indented to column ≥ 3; the previous 2-space
    // default collapsed nested ordered lists into a single flat list once
    // the message was sent and re-rendered.
    Markdown.configure({
      marked: sculptorMarked as unknown as typeof MarkedInstance,
      indentation: { style: "space", size: 4 },
    }),
    CustomCodeBlockLowlight.configure({ lowlight }) as Extension<unknown, unknown>,
    // Single `mention` node covering all three chip variants (@file, /skill,
    // +entity). The variant is identified by which attributes are populated:
    //   - `id` + mentionSuggestionChar "@" | "/"  → file / skill chip
    //   - `entityType` (+ entityId / entityDisplayName) → entity chip
    // Keeping one node means every chip shares the NodeView subscription,
    // arrow-key NodeSelection wiring, Enter-to-activate, and backspace/
    // delete behaviour.
    Mention.extend({
      addAttributes() {
        return {
          ...this.parent?.(),
          skillDescription: {
            default: null,
            parseHTML: (el: HTMLElement): string | null => el.getAttribute("data-skill-description"),
          },
          skillType: {
            default: null,
            parseHTML: (el: HTMLElement): string | null => el.getAttribute("data-skill-type"),
          },
          entityType: {
            default: null,
            parseHTML: (el: HTMLElement): string | null => el.getAttribute("data-entity-type"),
            renderHTML: (attributes: Record<string, unknown>): Record<string, string> =>
              attributes.entityType ? { "data-entity-type": String(attributes.entityType) } : {},
          },
          entityId: {
            default: null,
            parseHTML: (el: HTMLElement): string | null => el.getAttribute("data-entity-id"),
            renderHTML: (attributes: Record<string, unknown>): Record<string, string> =>
              attributes.entityId ? { "data-entity-id": String(attributes.entityId) } : {},
          },
          entityDisplayName: {
            default: null,
            parseHTML: (el: HTMLElement): string | null => el.getAttribute("data-entity-display-name"),
            renderHTML: (attributes: Record<string, unknown>): Record<string, string> =>
              attributes.entityDisplayName ? { "data-entity-display-name": String(attributes.entityDisplayName) } : {},
          },
        };
      },
      addNodeView() {
        return ReactNodeViewRenderer(MentionNodeView, { as: "span", className: "" });
      },
      // Arrow navigation across a chip goes through a "chip selected" state
      // (ProseMirror NodeSelection) before skipping to the other side. From
      // that state, Backspace/Delete removes the chip via ProseMirror's
      // default `deleteSelection` binding, Enter triggers the same action
      // as clicking the chip, and the next arrow press moves the cursor
      // past the chip.
      addKeyboardShortcuts() {
        const selectAdjacent = (direction: "before" | "after"): boolean => {
          const { state, view } = this.editor;
          const { selection, doc } = state;
          if (!(selection instanceof TextSelection) || !selection.empty) return false;
          const $pos = selection.$from;
          const adjacent = direction === "before" ? $pos.nodeBefore : $pos.nodeAfter;
          if (!adjacent || adjacent.type.name !== this.name) return false;
          const mentionPos = direction === "before" ? $pos.pos - adjacent.nodeSize : $pos.pos;
          view.dispatch(state.tr.setSelection(NodeSelection.create(doc, mentionPos)));
          return true;
        };

        const activateSelectedChip = (): boolean => {
          const { state, view } = this.editor;
          const { selection } = state;
          if (!(selection instanceof NodeSelection) || selection.node.type.name !== this.name) return false;
          const attrs = selection.node.attrs;
          const id = attrs.id;
          const entityType = attrs.entityType;
          // Skill chips (`/foo`) have no click action — let Enter bubble to
          // the chat's send-message binding. Entity repository chips are
          // also non-clickable (see EntityMentionChip.isClickable).
          const isSkill = typeof id === "string" && id.startsWith("/");
          const isRepository = entityType === "repository";
          if (isSkill || isRepository) return false;
          // File mentions carry the ElementIds.MENTION_SPAN testid; entity
          // mentions carry ELEMENT_IDS.ENTITY_MENTION_CHIP. Query for either.
          const dom = view.nodeDOM(selection.from);
          const chip =
            dom instanceof HTMLElement
              ? (dom.querySelector<HTMLElement>(`[data-testid="${ElementIds.MENTION_SPAN}"]`) ??
                dom.querySelector<HTMLElement>(`[data-testid="${ElementIds.ENTITY_MENTION_CHIP}"]`))
              : null;
          if (!chip) return false;
          chip.click();
          return true;
        };
        return {
          ArrowLeft: (): boolean => selectAdjacent("before"),
          ArrowRight: (): boolean => selectAdjacent("after"),
          Enter: (): boolean => activateSelectedChip(),
        };
      },
      // Allow the various wrapper formats produced by `renderMarkdown` (file/
      // skill: `<span data-sculptor-node>`; entity: `<span data-entity-type>`)
      // to be parsed back into the Mention node when restoring a draft.
      parseHTML() {
        return [
          // Default rule: <span data-type="mention">
          ...(this.parent?.() ?? []),
          // Entity variant — listed before the sculptor-node rule so an
          // entity span that also happens to carry data-sculptor-node wouldn't
          // be mis-parsed as a file mention. Populates only entity-* attrs.
          {
            tag: "span[data-entity-type]",
            getAttrs: (element: HTMLElement): Record<string, string | null> => ({
              entityType: element.getAttribute("data-entity-type"),
              entityId: element.getAttribute("data-entity-id"),
              entityDisplayName: element.getAttribute("data-entity-display-name"),
            }),
          },
          // Sculptor draft serialisation format (file + skill chips only —
          // entity chips serialise to the `+[…]` markdown shorthand which is
          // re-hydrated by the `+[…]` scanner in TipTapViewer).
          {
            tag: "span[data-sculptor-node]",
            getAttrs: (element: HTMLElement): Record<string, string | null> => {
              const text = element.textContent ?? "";
              const isSkill = text.startsWith("/");
              return {
                id: text,
                label: text,
                mentionSuggestionChar: isSkill ? "/" : "@",
                // Skill chip hover metadata. Absent for file @-mentions; for
                // skill /-mentions these were written by `renderMarkdown`.
                skillDescription: element.getAttribute("data-skill-description"),
                skillType: element.getAttribute("data-skill-type"),
              };
            },
          },
        ];
      },
      renderMarkdown(node): string {
        const entityType = node.attrs?.entityType as string | null | undefined;
        if (entityType) {
          // Entity chips round-trip as a compact `+[type:id|displayName]`
          // token. The backend forwards it verbatim; AlphaMarkdownBlock and
          // TipTapViewer re-hydrate it to a chip via regex.
          const entityId = String(node.attrs?.entityId ?? "");
          const entityDisplayName = String(node.attrs?.entityDisplayName ?? "");
          return `+[${entityType}:${entityId}|${entityDisplayName}]`;
        }
        const id = node.attrs?.id ?? "";
        const skillDescription = node.attrs?.skillDescription as string | null | undefined;
        const skillType = node.attrs?.skillType as string | null | undefined;
        // Wrap both file (@) and skill (/) mentions in a sculptor span so
        // the chip survives a round-trip through localStorage. Skill metadata
        // (description + type) is carried in data-* attrs so the hover card
        // can re-render the badge and description after a draft restore.
        // The backend strips these wrappers before forwarding the message to
        // the agent (see _strip_and_unescape_html in process_manager_utils.py).
        const descAttr = skillDescription ? ` data-skill-description="${escapeHtmlAttr(skillDescription)}"` : "";
        const typeAttr = skillType ? ` data-skill-type="${escapeHtmlAttr(skillType)}"` : "";
        return `<span data-sculptor-node${descAttr}${typeAttr}>${id}</span>`;
      },
    }).configure({
      ...(editable && (projectID || workspaceID || entityDataRef)
        ? {
            suggestions: [
              // CAPABILITY-GAP: supportsFileReferences — the @-mention file/folder picker resolves path references the agent reads itself; both Claude and pi report true today, so no harness suppresses it yet. createTipTapExtensions has no taskID, so gate here (thread the capability through Editor) when a harness reports !supportsFileReferences.
              ...(workspaceID && projectID ? [createFileSuggestion(projectID, workspaceID)] : []),
              // CAPABILITY-GAP: supportsSkills — slash-command skill picker fetches the full skill list regardless of harness; pi has no skills layer, so the items should be suppressed at the picker source when the active task's harness reports !supportsSkills.
              ...(workspaceID
                ? [createSkillSuggestion({ workspaceID })]
                : projectID
                  ? [createSkillSuggestion({ projectID })]
                  : []),
              // The prefilter picker is reachable via `+`. Agents, workspaces,
              // and repos are one row away from the `+` menu, which is the
              // same surface users already know for files and skills.
              createMentionPickerSuggestion({ projectID, workspaceID, entityDataRef, onTriggerImageUpload }),
            ],
          }
        : {}),
      HTMLAttributes: {
        class: styles.mention,
      },
      renderHTML({ options, node }) {
        // Entity variant: render with the entity testid + data-* attrs and
        // use the display name as text content. `class` intentionally stays
        // on `styles.mention` for static HTML callers (tests, getHTML()) —
        // the live NodeView replaces this anyway with the colored EntityChip.
        if (node.attrs.entityType) {
          const attrs = {
            ...options.HTMLAttributes,
            "data-testid": ElementIds.ENTITY_MENTION_CHIP,
            "data-entity-type": String(node.attrs.entityType),
            "data-entity-id": String(node.attrs.entityId ?? ""),
            "data-entity-display-name": String(node.attrs.entityDisplayName ?? ""),
          };
          return ["span", attrs, `${node.attrs.entityDisplayName ?? ""}`];
        }
        const baseAttrs =
          node.attrs.mentionSuggestionChar === "/"
            ? { ...options.HTMLAttributes, class: styles.skill }
            : options.HTMLAttributes;
        const attrs = { ...baseAttrs, "data-testid": ElementIds.MENTION_SPAN };
        return ["span", attrs, `${node.attrs.id}`];
      },
      deleteTriggerWithBackspace: true,
    }) as Extension<unknown, unknown>,
    Extension.create({
      name: "PreventEnter",
      addKeyboardShortcuts() {
        return {
          "Mod-Enter": (): boolean => true, // Return true and do nothing else
        };
      },
    }),
  ];

  // Only add placeholder for editable mode
  if (editable && placeholder) {
    extensions.push(
      Placeholder.configure({
        // Only show the placeholder when the entire editor is empty — not on
        // individual empty paragraphs within multi-paragraph content.  Without
        // this, pressing Enter at the start of text creates an empty first
        // paragraph that incorrectly displays the placeholder.
        placeholder: ({ editor }) => (editor.isEmpty ? placeholder : ""),
        emptyNodeClass: styles.placeholder,
        showOnlyCurrent: false,
      }),
    );
  }

  return extensions;
};
