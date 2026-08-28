import type { JSONContent } from "@tiptap/react";
import { Editor } from "@tiptap/react";
import { describe, expect, it } from "vitest";

import { typeText } from "./codeBlockExtension.testUtils.ts";
import { hydrateEntityMentions } from "./entityMentionHydration.ts";
import { createTipTapExtensions } from "./tipTapConfig.ts";

/**
 * Tests that the TipTap editor serializes prompts correctly and that the
 * viewer re-parses them without losing content or adding artifacts.
 *
 * CustomParagraph serializes empty paragraphs as "\u200B" (zero-width space)
 * to avoid two known issues:
 *  - "&nbsp;" (the default) appears as literal text after a round-trip.
 *  - "\u00A0" (NBSP) matches /^\s/, so the ordered list tokenizer treats it
 *    as indented continuation content, swallowing text after a list.
 *
 * \u200B does not match /^\s/ and is real content, so paragraphs survive a
 * round-trip without interfering with list parsing.
 */
describe("prompt serialization and round-trip", () => {
  const createEditableEditor = (): Editor => {
    const extensions = createTipTapExtensions({ editable: true });
    return new Editor({ extensions });
  };

  const createViewerEditor = (markdown: string): Editor => {
    const extensions = createTipTapExtensions({ editable: false });
    return new Editor({
      extensions,
      content: markdown,
      contentType: "markdown" as const,
    });
  };

  // -- List followed by text --------------------------------------------------

  it("list followed by text: trailing text is preserved outside the list", () => {
    const editor = createEditableEditor();
    editor.commands.toggleOrderedList();
    editor.commands.insertContent("X");
    editor.commands.splitListItem("listItem");
    editor.commands.insertContent("Y");
    editor.commands.splitListItem("listItem");
    editor.commands.liftListItem("listItem");
    editor.commands.insertContent("Z");

    const md = editor.getMarkdown();
    expect(md).not.toContain("\u00A0");
    expect(md).toContain("\n\nZ");
    editor.destroy();

    const viewer = createViewerEditor(md);
    const html = viewer.getHTML();
    expect(html).toContain("<p>Z</p>");
    expect(html).not.toMatch(/<li>.*Z.*<\/li>/);
    viewer.destroy();
  });

  it("long list followed by text: trailing text is preserved", () => {
    const editor = createEditableEditor();
    editor.commands.toggleOrderedList();
    editor.commands.insertContent("Desktop setup with alarms");
    editor.commands.splitListItem("listItem");
    editor.commands.insertContent("Walk 15 minutes to station");
    editor.commands.splitListItem("listItem");
    editor.commands.insertContent("Bart-to-Bart transfer");
    editor.commands.splitListItem("listItem");
    editor.commands.insertContent("Route setup for each side");
    editor.commands.splitListItem("listItem");
    editor.commands.liftListItem("listItem");
    editor.commands.insertContent("goodnight");

    const md = editor.getMarkdown();
    expect(md).not.toContain("\u00A0");
    expect(md).toContain("goodnight");
    editor.destroy();

    const viewer = createViewerEditor(md);
    const html = viewer.getHTML();
    expect(html).toContain("goodnight");
    expect(html).not.toMatch(/<li>.*goodnight.*<\/li>/);
    viewer.destroy();
  });

  // -- Trailing empty paragraph -----------------------------------------------

  it("trailing empty paragraph does not produce an extra blank line", () => {
    const editor = createEditableEditor();
    editor.commands.toggleOrderedList();
    editor.commands.insertContent("A");
    editor.commands.splitListItem("listItem");
    editor.commands.insertContent("B");
    editor.commands.splitListItem("listItem");
    editor.commands.liftListItem("listItem");

    const md = editor.getMarkdown();
    editor.destroy();

    // Strip trailing ZWSP lines the same way the display path does
    const stripped = md.replace(/(\n\n[\u200B\u00A0])+$/, "");
    const viewer = createViewerEditor(stripped);
    const json = viewer.getJSON();
    const topLevel = json.content ?? [];
    const trailingParagraphs = topLevel.filter(
      (n, i) => i > 0 && n.type === "paragraph" && (!n.content || n.content.length === 0),
    );
    expect(trailingParagraphs).toHaveLength(0);
    viewer.destroy();
  });

  // -- Empty paragraphs between content survive round-trip --------------------

  it("empty paragraphs between content survive a round-trip", () => {
    const editor = createEditableEditor();
    editor.commands.insertContent("A");
    editor.commands.enter();
    editor.commands.enter();
    editor.commands.insertContent("B");

    const md = editor.getMarkdown();
    editor.destroy();

    const viewer = createViewerEditor(md);
    const html = viewer.getHTML();
    expect(html).toContain("<p>A</p>");
    expect(html).toContain("<p>B</p>");

    const json = viewer.getJSON();
    const paragraphs = json.content?.filter((n) => n.type === "paragraph") ?? [];
    expect(paragraphs.length).toBeGreaterThanOrEqual(3);
    viewer.destroy();
  });

  // -- ZWSP does not match whitespace regex -----------------------------------

  it("ZWSP does not match INDENTED_LINE_REGEX, NBSP does", () => {
    const INDENTED_LINE_REGEX = /^\s/;
    expect(INDENTED_LINE_REGEX.test("\u00A0")).toBe(true);
    expect(INDENTED_LINE_REGEX.test("\u200B")).toBe(false);
  });

  // -- Legacy NBSP markdown still displays correctly --------------------------

  it("viewer handles legacy NBSP markdown without losing content", () => {
    const markdown = "1. X\n2. Y\n\nZ\n\n\u00A0";
    const viewer = createViewerEditor(markdown);
    expect(viewer.getHTML()).toContain("<p>Z</p>");
    viewer.destroy();
  });

  // -- Markdown special characters round-trip ---------------------------------

  it("asterisks in plain text survive round-trip without becoming italic", () => {
    const editor = createEditableEditor();
    editor.commands.insertContent("use *args in python");
    const md = editor.getMarkdown();
    editor.destroy();

    const viewer = createViewerEditor(md);
    const text = viewer.getText();
    expect(text).toContain("*args");
    // Should NOT have <em> tags — the asterisk is literal, not formatting
    const html = viewer.getHTML();
    expect(html).not.toContain("<em>");
    viewer.destroy();
  });

  it("underscores in plain text survive round-trip without becoming italic", () => {
    const editor = createEditableEditor();
    editor.commands.insertContent("my_var_name");
    const md = editor.getMarkdown();
    editor.destroy();

    const viewer = createViewerEditor(md);
    const text = viewer.getText();
    expect(text).toContain("my_var_name");
    const html = viewer.getHTML();
    expect(html).not.toContain("<em>");
    viewer.destroy();
  });

  it("markdown special chars inserted via insertContent are escaped", () => {
    // insertContent inserts plain text — markdown characters should be
    // escaped during serialization so they round-trip as literal text.
    const cases = [
      { input: "use *args and **kwargs", mustContain: "*args", mustNotContainTag: "<em>" },
      { input: "my_var_name", mustContain: "my_var_name", mustNotContainTag: "<em>" },
      { input: "price is $100", mustContain: "$100", mustNotContainTag: undefined },
      { input: "a > b && c < d", mustContain: "a > b", mustNotContainTag: "<blockquote>" },
    ];

    for (const { input, mustContain, mustNotContainTag } of cases) {
      const editor = createEditableEditor();
      editor.commands.insertContent(input);
      const md = editor.getMarkdown();
      editor.destroy();

      const viewer = createViewerEditor(md);
      expect(viewer.getText()).toContain(mustContain);
      if (mustNotContainTag) {
        expect(viewer.getHTML()).not.toContain(mustNotContainTag);
      }
      viewer.destroy();
    }
  });
});

describe("mention node markdown round-trip", () => {
  const createEditableEditor = (): Editor => {
    return new Editor({ extensions: createTipTapExtensions({ editable: true }) });
  };

  const createEditorFromMarkdown = (markdown: string): Editor => {
    const editor = new Editor({ extensions: createTipTapExtensions({ editable: true }) });
    editor.commands.setContent(markdown, { contentType: "markdown" });
    return editor;
  };

  type MentionAttrs = {
    id?: string | null;
    label?: string | null;
    mentionSuggestionChar?: string | null;
    skillDescription?: string | null;
    skillType?: string | null;
    entityType?: string | null;
    entityId?: string | null;
    entityDisplayName?: string | null;
  };

  const findMentionNodes = (json: JSONContent): Array<MentionAttrs> => {
    const out: Array<MentionAttrs> = [];
    const walk = (node: JSONContent): void => {
      if (node.type === "mention") out.push((node.attrs ?? {}) as MentionAttrs);
      const children = (node.content ?? []) as Array<JSONContent>;
      for (const child of children) walk(child);
    };
    walk(json);
    return out;
  };

  const insertMentionNode = (editor: Editor, attrs: MentionAttrs): void => {
    editor
      .chain()
      .focus()
      .insertContent({ type: "mention", attrs: attrs as Record<string, unknown> })
      .run();
  };

  it("file mention round-trips as a sculptor-node span", () => {
    const editor = createEditableEditor();
    insertMentionNode(editor, { id: "@src/utils.ts", label: "@src/utils.ts", mentionSuggestionChar: "@" });
    const md = editor.getMarkdown();
    editor.destroy();

    expect(md).toContain("data-sculptor-node");
    expect(md).toContain("@src/utils.ts");

    const restored = createEditorFromMarkdown(md);
    const mentions = findMentionNodes(restored.getJSON());
    expect(mentions).toHaveLength(1);
    expect(mentions[0].id).toBe("@src/utils.ts");
    expect(mentions[0].mentionSuggestionChar).toBe("@");
    expect(mentions[0].entityType ?? null).toBeNull();
    restored.destroy();
  });

  it("skill mention round-trips with description and type metadata", () => {
    const editor = createEditableEditor();
    insertMentionNode(editor, {
      id: "/review",
      label: "/review",
      mentionSuggestionChar: "/",
      skillDescription: "Review a pull request",
      skillType: "builtin",
    });
    const md = editor.getMarkdown();
    editor.destroy();

    expect(md).toContain('data-skill-description="Review a pull request"');
    expect(md).toContain('data-skill-type="builtin"');

    const restored = createEditorFromMarkdown(md);
    const mentions = findMentionNodes(restored.getJSON());
    expect(mentions).toHaveLength(1);
    expect(mentions[0].id).toBe("/review");
    expect(mentions[0].mentionSuggestionChar).toBe("/");
    expect(mentions[0].skillDescription).toBe("Review a pull request");
    expect(mentions[0].skillType).toBe("builtin");
    restored.destroy();
  });

  it("bare skill mention round-trips with null metadata", () => {
    const editor = createEditableEditor();
    insertMentionNode(editor, { id: "/clear", label: "/clear", mentionSuggestionChar: "/" });
    const md = editor.getMarkdown();
    editor.destroy();

    const restored = createEditorFromMarkdown(md);
    const mentions = findMentionNodes(restored.getJSON());
    expect(mentions).toHaveLength(1);
    expect(mentions[0].skillDescription ?? null).toBeNull();
    expect(mentions[0].skillType ?? null).toBeNull();
    restored.destroy();
  });

  it.each(["workspace", "repository", "agent"] as const)(
    "%s entity mention round-trips through +[…] and hydrates back",
    (entityType) => {
      const editor = createEditableEditor();
      insertMentionNode(editor, {
        entityType,
        entityId: `${entityType}_abc`,
        entityDisplayName: `My ${entityType}`,
      });
      const md = editor.getMarkdown();
      editor.destroy();

      // Compact entity token, not a sculptor-node span.
      expect(md).toContain(`+[${entityType}:${entityType}_abc|My ${entityType}]`);
      expect(md).not.toContain("data-sculptor-node");

      // Before hydration the parser leaves +[…] as literal text.
      const restored = createEditorFromMarkdown(md);
      expect(findMentionNodes(restored.getJSON())).toHaveLength(0);

      hydrateEntityMentions(restored);

      const mentions = findMentionNodes(restored.getJSON());
      expect(mentions).toHaveLength(1);
      expect(mentions[0].entityType).toBe(entityType);
      expect(mentions[0].entityId).toBe(`${entityType}_abc`);
      expect(mentions[0].entityDisplayName).toBe(`My ${entityType}`);
      restored.destroy();
    },
  );

  it("mixed text + file mention + entity mention round-trips together", () => {
    const editor = createEditableEditor();
    editor.commands.insertContent("Hello ");
    insertMentionNode(editor, { id: "@foo.txt", label: "@foo.txt", mentionSuggestionChar: "@" });
    editor.commands.insertContent(" and ");
    insertMentionNode(editor, {
      entityType: "workspace",
      entityId: "ws_1",
      entityDisplayName: "My WS",
    });
    const md = editor.getMarkdown();
    editor.destroy();

    expect(md).toContain("Hello");
    expect(md).toContain("@foo.txt");
    expect(md).toContain("+[workspace:ws_1|My WS]");

    const restored = createEditorFromMarkdown(md);
    hydrateEntityMentions(restored);

    const mentions = findMentionNodes(restored.getJSON());
    expect(mentions).toHaveLength(2);
    const file = mentions.find((m) => m.id === "@foo.txt");
    const entity = mentions.find((m) => m.entityType === "workspace");
    expect(file?.mentionSuggestionChar).toBe("@");
    expect(entity?.entityId).toBe("ws_1");
    expect(restored.getText()).toContain("Hello");
    expect(restored.getText()).toContain("and");
    restored.destroy();
  });

  it("mention inside a bullet list survives round-trip", () => {
    const editor = createEditableEditor();
    editor.commands.toggleBulletList();
    insertMentionNode(editor, { id: "@README.md", label: "@README.md", mentionSuggestionChar: "@" });
    const md = editor.getMarkdown();
    editor.destroy();

    expect(md).toMatch(/^\s*[-*]\s/m);
    expect(md).toContain("@README.md");

    const restored = createEditorFromMarkdown(md);
    const mentions = findMentionNodes(restored.getJSON());
    expect(mentions).toHaveLength(1);
    expect(mentions[0].id).toBe("@README.md");
    restored.destroy();
  });

  it("multiple entity mentions in one paragraph round-trip and hydrate", () => {
    const editor = createEditableEditor();
    insertMentionNode(editor, { entityType: "workspace", entityId: "1", entityDisplayName: "A" });
    editor.commands.insertContent(" ");
    insertMentionNode(editor, { entityType: "repository", entityId: "2", entityDisplayName: "B" });
    const md = editor.getMarkdown();
    editor.destroy();

    expect(md).toContain("+[workspace:1|A]");
    expect(md).toContain("+[repository:2|B]");

    const restored = createEditorFromMarkdown(md);
    hydrateEntityMentions(restored);
    const mentions = findMentionNodes(restored.getJSON());
    expect(mentions).toHaveLength(2);
    expect(mentions.map((m) => m.entityId).sort()).toEqual(["1", "2"]);
    restored.destroy();
  });
});

/**
 * The ``+`` mention trigger must not also fire TipTap's BulletList input
 * rule. TipTap's stock BulletList treats ``+ ``/``* ``/``- `` at line start
 * as a markdown shortcut to start a bullet list. Sculptor's
 * CustomBulletList in TipTapConfig drops ``+`` from the trigger set so the
 * picker can own that character.
 */
describe("CustomBulletList — bullet-list shortcut on + is disabled", () => {
  const createEditableEditor = (): Editor => {
    return new Editor({ extensions: createTipTapExtensions({ editable: true }) });
  };

  const isBulletList = (node: JSONContent | undefined): boolean => {
    return node?.type === "bulletList";
  };

  it("typing '+ ' at the start of a line does not produce a bullet list", () => {
    const editor = createEditableEditor();
    editor.commands.setContent("");
    editor.commands.focus();
    // ``typeText`` routes each character through ``handleTextInput`` so the
    // bullet-list input rule actually fires — a plain ``tr.insertText``
    // bypasses the input-rule plugin and would pass even if the override
    // were removed.
    typeText(editor, "+ ");
    const json = editor.getJSON();
    const topLevel = json.content ?? [];
    expect(topLevel.some(isBulletList)).toBe(false);
    editor.destroy();
  });

  it("typing '- ' at the start of a line still produces a bullet list (sanity check)", () => {
    // Confirms only ``+`` was dropped from the input rule's trigger set; the
    // other trigger characters still start a list when typed. If this stops
    // working, the override has gone too far and removed all triggers.
    const editor = createEditableEditor();
    editor.commands.setContent("");
    editor.commands.focus();
    typeText(editor, "- ");
    const json = editor.getJSON();
    const topLevel = json.content ?? [];
    expect(topLevel.some(isBulletList)).toBe(true);
    editor.destroy();
  });
});
