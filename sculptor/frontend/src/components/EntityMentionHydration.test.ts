import type { JSONContent } from "@tiptap/react";
import { Editor } from "@tiptap/react";
import { afterEach, describe, expect, it } from "vitest";

import { hydrateEntityMentions } from "./EntityMentionHydration.ts";
import { createTipTapExtensions } from "./TipTapConfig.ts";

const editors: Array<Editor> = [];

afterEach(() => {
  while (editors.length > 0) {
    const editor = editors.pop();
    if (editor && !editor.isDestroyed) editor.destroy();
  }
});

function trackedEditor(): Editor {
  const editor = new Editor({ extensions: createTipTapExtensions({ editable: false }) });
  editors.push(editor);
  return editor;
}

function setPlainTextParagraphs(editor: Editor, paragraphs: Array<string>): void {
  const doc: JSONContent = {
    type: "doc",
    content: paragraphs.map((text) => ({
      type: "paragraph",
      content: text === "" ? [] : [{ type: "text", text }],
    })),
  };
  editor.commands.setContent(doc as Parameters<typeof editor.commands.setContent>[0]);
}

type CollectedMention = {
  entityType: string | null | undefined;
  entityId: string | null | undefined;
  entityDisplayName: string | null | undefined;
};

function collectMentionNodes(editor: Editor): Array<CollectedMention> {
  const out: Array<CollectedMention> = [];
  const walk = (node: JSONContent): void => {
    if (node.type === "mention") {
      const attrs = (node.attrs ?? {}) as CollectedMention;
      out.push({
        entityType: attrs.entityType,
        entityId: attrs.entityId,
        entityDisplayName: attrs.entityDisplayName,
      });
    }
    const children = (node.content ?? []) as Array<JSONContent>;
    for (const child of children) walk(child);
  };
  walk(editor.getJSON());
  return out;
}

function collectTextContent(editor: Editor): string {
  return editor.getText();
}

describe("hydrateEntityMentions — single token", () => {
  it("replaces a lone token with a mention node carrying entity attrs", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["+[workspace:ws_1|My Workspace]"]);

    hydrateEntityMentions(editor);

    const mentions = collectMentionNodes(editor);
    expect(mentions).toHaveLength(1);
    expect(mentions[0]).toEqual({
      entityType: "workspace",
      entityId: "ws_1",
      entityDisplayName: "My Workspace",
    });
  });

  it("preserves surrounding text", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["before +[agent:a_1|My Agent] after"]);

    hydrateEntityMentions(editor);

    expect(collectTextContent(editor)).toContain("before");
    expect(collectTextContent(editor)).toContain("after");
    expect(collectTextContent(editor)).not.toContain("+[");
  });
});

describe("hydrateEntityMentions — idempotency", () => {
  it("running twice yields the same JSON as running once", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["+[workspace:w|W] +[repository:r|R]"]);

    hydrateEntityMentions(editor);
    const onceJson = JSON.stringify(editor.getJSON());

    hydrateEntityMentions(editor);
    const twiceJson = JSON.stringify(editor.getJSON());

    expect(twiceJson).toEqual(onceJson);
  });
});

describe("hydrateEntityMentions — multiple tokens in one paragraph", () => {
  it("replaces three tokens, preserving order and indices", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["+[workspace:a|A] +[workspace:b|B] +[workspace:c|C]"]);

    hydrateEntityMentions(editor);

    const mentions = collectMentionNodes(editor);
    expect(mentions).toHaveLength(3);
    expect(mentions.map((m) => m.entityId)).toEqual(["a", "b", "c"]);
  });
});

describe("hydrateEntityMentions — tokens across paragraphs", () => {
  it("replaces tokens in multiple paragraphs", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, [
      "first +[workspace:w1|One]",
      "second +[agent:t1|Agent] tail",
      "third +[repository:r1|Repo]",
    ]);

    hydrateEntityMentions(editor);

    const mentions = collectMentionNodes(editor);
    expect(mentions).toHaveLength(3);
    expect(mentions.map((m) => m.entityId).sort()).toEqual(["r1", "t1", "w1"]);
    expect(collectTextContent(editor)).not.toContain("+[");
  });

  it("replaces a token in a later paragraph when earlier paragraphs are token-free", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["plain first paragraph", "tail +[workspace:w1|Main] end"]);

    hydrateEntityMentions(editor);

    const mentions = collectMentionNodes(editor);
    expect(mentions).toHaveLength(1);
    expect(mentions[0]).toEqual({
      entityType: "workspace",
      entityId: "w1",
      entityDisplayName: "Main",
    });
  });
});

describe("hydrateEntityMentions — no tokens", () => {
  it("leaves a doc with no +[…] tokens structurally identical and dispatches no transaction", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["plain text", "another paragraph with no tokens"]);
    const before = JSON.stringify(editor.getJSON());
    const docBefore = editor.state.doc;

    hydrateEntityMentions(editor);

    expect(JSON.stringify(editor.getJSON())).toEqual(before);
    // Same doc reference proves no transaction was dispatched.
    expect(editor.state.doc).toBe(docBefore);
  });
});

describe("hydrateEntityMentions — already-hydrated mention nodes", () => {
  it("leaves an existing mention node alone (it isn't a text node)", () => {
    const editor = trackedEditor();
    editor
      .chain()
      .focus()
      .insertContent({
        type: "mention",
        attrs: { entityType: "workspace", entityId: "w", entityDisplayName: "W" },
      })
      .run();
    const before = JSON.stringify(editor.getJSON());

    hydrateEntityMentions(editor);

    expect(JSON.stringify(editor.getJSON())).toEqual(before);
    expect(collectMentionNodes(editor)).toHaveLength(1);
  });
});

describe("hydrateEntityMentions — malformed tokens", () => {
  const cases: Array<{ name: string; text: string }> = [
    { name: "no pipe", text: "+[workspace:abc|]" },
    { name: "truncated bracket", text: "+[workspace:abc|name" },
    { name: "missing colon", text: "+[workspace_abc|name]" },
    { name: "empty type", text: "+[:abc|name]" },
    { name: "empty id", text: "+[workspace:|name]" },
  ];

  for (const { name, text } of cases) {
    it(`leaves "${name}" tokens as literal text`, () => {
      const editor = trackedEditor();
      setPlainTextParagraphs(editor, [text]);

      hydrateEntityMentions(editor);

      expect(collectMentionNodes(editor)).toHaveLength(0);
      expect(collectTextContent(editor)).toContain("+[");
    });
  }
});

describe("hydrateEntityMentions — display names with allowed special chars", () => {
  it("hydrates names containing spaces, hyphens, dots, and version numbers", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["+[workspace:abc-123|My Workspace v2.0]"]);

    hydrateEntityMentions(editor);

    const mentions = collectMentionNodes(editor);
    expect(mentions).toHaveLength(1);
    expect(mentions[0]).toEqual({
      entityType: "workspace",
      entityId: "abc-123",
      entityDisplayName: "My Workspace v2.0",
    });
  });
});

describe("hydrateEntityMentions — mixed entity types", () => {
  it("hydrates workspace, repository, and agent tokens together", () => {
    const editor = trackedEditor();
    setPlainTextParagraphs(editor, ["+[workspace:w|W] +[repository:r|R] +[agent:a|A]"]);

    hydrateEntityMentions(editor);

    const mentions = collectMentionNodes(editor);
    expect(mentions).toHaveLength(3);
    expect(mentions.map((m) => m.entityType).sort()).toEqual(["agent", "repository", "workspace"]);
  });
});

describe("hydrateEntityMentions — code regions are preserved verbatim", () => {
  it("does not re-parse a token wrapped in an inline code mark", () => {
    // Reproduces a user-reported bug: typing `+[workspace:…|Agent 1]`
    // inside backticks survives the initial render as code, but a draft
    // round-trip through markdown re-ran hydration over the code-marked
    // text and produced an unintended chip. The fix gates hydration on
    // the presence of the `code` mark on the text node.
    const editor = trackedEditor();
    editor.commands.setContent({
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "literal " },
            {
              type: "text",
              text: "+[workspace:ws_1|Agent 1]",
              marks: [{ type: "code" }],
            },
            { type: "text", text: " end" },
          ],
        },
      ],
    } as Parameters<typeof editor.commands.setContent>[0]);

    hydrateEntityMentions(editor);

    expect(collectMentionNodes(editor)).toHaveLength(0);
    expect(collectTextContent(editor)).toContain("+[workspace:ws_1|Agent 1]");
  });

  it("does not re-parse a token inside a code block", () => {
    const editor = trackedEditor();
    editor.commands.setContent({
      type: "doc",
      content: [
        {
          type: "codeBlock",
          content: [{ type: "text", text: "+[workspace:ws_1|Agent 1]" }],
        },
      ],
    } as Parameters<typeof editor.commands.setContent>[0]);

    hydrateEntityMentions(editor);

    expect(collectMentionNodes(editor)).toHaveLength(0);
    expect(collectTextContent(editor)).toContain("+[workspace:ws_1|Agent 1]");
  });

  it("still hydrates a token in regular text in the same paragraph as a code-marked token", () => {
    const editor = trackedEditor();
    editor.commands.setContent({
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            {
              type: "text",
              text: "+[workspace:ws_code|InCode]",
              marks: [{ type: "code" }],
            },
            { type: "text", text: " then +[workspace:ws_live|Live]" },
          ],
        },
      ],
    } as Parameters<typeof editor.commands.setContent>[0]);

    hydrateEntityMentions(editor);

    const mentions = collectMentionNodes(editor);
    expect(mentions).toHaveLength(1);
    expect(mentions[0]).toEqual({
      entityType: "workspace",
      entityId: "ws_live",
      entityDisplayName: "Live",
    });
    // Code-marked token survives as literal text.
    expect(collectTextContent(editor)).toContain("+[workspace:ws_code|InCode]");
  });
});
