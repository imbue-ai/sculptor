import type { Editor } from "@tiptap/core";
import { Editor as TipTapEditorClass } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Placeholder from "@tiptap/extension-placeholder";
import Text from "@tiptap/extension-text";
import { Markdown } from "@tiptap/markdown";
import { common, createLowlight } from "lowlight";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { CustomCodeBlockLowlight } from "./CodeBlockExtension";
import { dedentText } from "./CodeBlockExtension";
import { createTestEditor, simulatePaste, typeText } from "./CodeBlockExtension.testUtils";
import styles from "./Editor.module.scss";

const lowlight = createLowlight(common);

describe("dedentText", () => {
  it("strips minimum common leading whitespace", () => {
    const input = "    const a = 1;\n    const b = 2;\n    const c = 3;";
    const expected = "const a = 1;\nconst b = 2;\nconst c = 3;";
    expect(dedentText(input)).toBe(expected);
  });

  it("preserves relative indentation", () => {
    const input = "    function foo() {\n        return 1;\n    }";
    const expected = "function foo() {\n    return 1;\n}";
    expect(dedentText(input)).toBe(expected);
  });

  it("returns text unchanged when no common indentation", () => {
    const input = "const a = 1;\n  const b = 2;";
    expect(dedentText(input)).toBe(input);
  });

  it("ignores empty lines when calculating minimum indent", () => {
    const input = "    line1\n\n    line2";
    const expected = "line1\n\nline2";
    expect(dedentText(input)).toBe(expected);
  });

  it("handles single line input", () => {
    const input = "    const a = 1;";
    expect(dedentText(input)).toBe("const a = 1;");
  });

  it("returns empty string unchanged", () => {
    expect(dedentText("")).toBe("");
  });

  it("returns whitespace-only lines unchanged", () => {
    const input = "   \n   ";
    expect(dedentText(input)).toBe(input);
  });

  it("handles tab indentation", () => {
    const input = "\t\tconst a = 1;\n\t\tconst b = 2;";
    const expected = "const a = 1;\nconst b = 2;";
    expect(dedentText(input)).toBe(expected);
  });

  it("handles mixed indent where first line has extra space", () => {
    const input = " const codePath = env;\nconst openWith = src;\nconst copy = openWith;";
    expect(dedentText(input)).toBe(input);
  });
});

describe("CustomCodeBlockLowlight input rules", () => {
  let editor: Editor;

  beforeEach(() => {
    editor = createTestEditor();
  });

  afterEach(() => {
    editor.destroy();
  });

  it("creates a code block when ``` is typed at start of line", () => {
    typeText(editor, "```");

    const doc = editor.state.doc;
    expect(doc.child(0).type.name).toBe("codeBlock");
    expect(doc.child(0).textContent).toBe("");
  });

  it("creates a code block and includes text after cursor", () => {
    // Insert text first, then move cursor to start and type ```
    editor.commands.insertContent("hello world");
    editor.commands.focus("start");
    typeText(editor, "```");

    const doc = editor.state.doc;
    // The whole block should become a code block with "hello world" as content
    expect(doc.child(0).type.name).toBe("codeBlock");
    expect(doc.child(0).textContent).toBe("hello world");
  });

  it("splits line when ``` is typed in the middle", () => {
    typeText(editor, "hello ```");

    const doc = editor.state.doc;
    expect(doc.childCount).toBe(2);
    expect(doc.child(0).type.name).toBe("paragraph");
    expect(doc.child(0).textContent).toBe("hello ");
    expect(doc.child(1).type.name).toBe("codeBlock");
  });

  it("merges consecutive code blocks with a newline separator", () => {
    // Create a code block with some content
    typeText(editor, "```");
    typeText(editor, "line1");

    // Exit the code block (triple enter exits, leaving cursor after it)
    editor.commands.exitCode();

    // Create another code block — should merge with the first
    typeText(editor, "```");

    const doc = editor.state.doc;
    expect(doc.child(0).type.name).toBe("codeBlock");
    // The merged content should have a newline between the two blocks' content
    expect(doc.child(0).textContent).toContain("line1\n");
  });

  it("does not create code block when already inside one", () => {
    // Create a code block first
    typeText(editor, "```");
    expect(editor.state.doc.child(0).type.name).toBe("codeBlock");

    // Try typing ``` inside the code block — should not create a nested block
    typeText(editor, "```");
    expect(editor.state.doc.child(0).type.name).toBe("codeBlock");
    expect(editor.state.doc.child(0).textContent).toBe("```");
  });
});

describe("CustomCodeBlockLowlight paste handling", () => {
  let editor: Editor;

  beforeEach(() => {
    editor = createTestEditor();
  });

  afterEach(() => {
    editor.destroy();
  });

  it("dedents code pasted from VS Code", () => {
    const indentedCode = "    const a = 1;\n    const b = 2;";

    simulatePaste(editor, {
      "text/plain": indentedCode,
      "vscode-editor-data": JSON.stringify({ mode: "javascript" }),
    });

    const codeBlock = editor.state.doc.child(0);
    expect(codeBlock.type.name).toBe("codeBlock");
    expect(codeBlock.attrs.language).toBe("javascript");
    expect(codeBlock.textContent).toBe("const a = 1;\nconst b = 2;");
  });

  it("does not create VS Code code block when already inside one", () => {
    // Create a code block first
    typeText(editor, "```");
    expect(editor.state.doc.child(0).type.name).toBe("codeBlock");

    // Paste VS Code content — should not create a new code block
    simulatePaste(editor, {
      "text/plain": "hello",
      "vscode-editor-data": JSON.stringify({ mode: "javascript" }),
    });

    // Should still be a single code block (not nested)
    expect(editor.state.doc.childCount).toBe(1);
    expect(editor.state.doc.child(0).type.name).toBe("codeBlock");
  });

  it("dedents text pasted into an existing code block", () => {
    // Create a code block
    typeText(editor, "```");
    expect(editor.state.doc.child(0).type.name).toBe("codeBlock");

    const indentedCode = "    line1\n    line2";
    simulatePaste(editor, { "text/plain": indentedCode });

    expect(editor.state.doc.child(0).textContent).toBe("line1\nline2");
  });

  it("does not intercept paste when text has no common indentation", () => {
    // Create a code block
    typeText(editor, "```");

    const code = "line1\n  line2";
    const isHandled = simulatePaste(editor, { "text/plain": code });

    // Our dedent handler should return false (no common indent to strip),
    // letting ProseMirror's default paste handle it
    expect(isHandled).toBe(false);
  });
});

describe("Placeholder functionality", () => {
  it("exports a valid placeholder class from the CSS module", () => {
    // Verify that styles.placeholder is defined — if CSS Modules doesn't export
    // the class (e.g. because it's only used in a compound selector), the
    // Placeholder extension would receive undefined and never decorate nodes.
    expect(styles.placeholder).toBeDefined();
    expect(typeof styles.placeholder).toBe("string");
    expect(styles.placeholder.length).toBeGreaterThan(0);
  });

  it("adds placeholder decoration to empty paragraph on initialization", () => {
    const PLACEHOLDER_TEXT = "Enter a prompt...";

    const editor = new TipTapEditorClass({
      extensions: [
        Document,
        Paragraph,
        Text,
        CustomCodeBlockLowlight.configure({ lowlight }),
        Placeholder.configure({
          placeholder: PLACEHOLDER_TEXT,
          emptyNodeClass: "test-placeholder",
          showOnlyCurrent: false,
        }),
      ],
    });

    const firstP = editor.view.dom.querySelector("p");
    expect(firstP).not.toBeNull();
    expect(firstP!.classList.contains("test-placeholder")).toBe(true);
    expect(firstP!.getAttribute("data-placeholder")).toBe(PLACEHOLDER_TEXT);

    editor.destroy();
  });

  it("adds placeholder with the CSS module class name used in production", () => {
    const PLACEHOLDER_TEXT = "Enter a prompt (optional)...";

    const editor = new TipTapEditorClass({
      extensions: [
        Document,
        Paragraph,
        Text,
        CustomCodeBlockLowlight.configure({ lowlight }),
        Placeholder.configure({
          placeholder: PLACEHOLDER_TEXT,
          emptyNodeClass: styles.placeholder,
          showOnlyCurrent: false,
        }),
      ],
    });

    const firstP = editor.view.dom.querySelector("p");
    expect(firstP).not.toBeNull();
    expect(firstP!.classList.contains(styles.placeholder)).toBe(true);
    expect(firstP!.getAttribute("data-placeholder")).toBe(PLACEHOLDER_TEXT);

    editor.destroy();
  });

  it("renders paragraph when initialized with empty markdown content", () => {
    // Regression: @tiptap/markdown parses "" into a document with zero nodes,
    // so the editor renders no <p> and the placeholder is invisible. The fix
    // is to omit contentType when value is empty.
    const editor = new TipTapEditorClass({
      extensions: [
        Document,
        Paragraph,
        Text,
        Markdown,
        CustomCodeBlockLowlight.configure({ lowlight }),
        Placeholder.configure({
          placeholder: "Enter a prompt...",
          emptyNodeClass: "test-placeholder",
          showOnlyCurrent: false,
        }),
      ],
      // Simulate the fix: omit contentType when content is empty
      content: undefined,
    });

    // Document should have a paragraph even with no content
    const firstP = editor.view.dom.querySelector("p");
    expect(firstP).not.toBeNull();
    expect(firstP!.classList.contains("test-placeholder")).toBe(true);
    expect(firstP!.getAttribute("data-placeholder")).toBe("Enter a prompt...");

    editor.destroy();
  });

  it("does not create a paragraph when contentType markdown parses empty string", () => {
    // This test documents the @tiptap/markdown bug: parsing "" with
    // contentType: "markdown" produces an empty document.
    const editor = new TipTapEditorClass({
      extensions: [Document, Paragraph, Text, Markdown, CustomCodeBlockLowlight.configure({ lowlight })],
      content: "",
      contentType: "markdown",
    });

    // This demonstrates the bug: no paragraph is created
    const firstP = editor.view.dom.querySelector("p");
    expect(firstP).toBeNull();

    editor.destroy();
  });

  it("removes placeholder decoration when content is added", () => {
    const PLACEHOLDER_TEXT = "Enter a prompt...";

    const editor = new TipTapEditorClass({
      extensions: [
        Document,
        Paragraph,
        Text,
        CustomCodeBlockLowlight.configure({ lowlight }),
        Placeholder.configure({
          placeholder: PLACEHOLDER_TEXT,
          emptyNodeClass: "test-placeholder",
          showOnlyCurrent: false,
        }),
      ],
    });

    // First verify placeholder is present
    let firstP = editor.view.dom.querySelector("p");
    expect(firstP!.classList.contains("test-placeholder")).toBe(true);

    // Add content
    editor.commands.insertContent("hello");

    // Placeholder should be gone
    firstP = editor.view.dom.querySelector("p");
    expect(firstP).not.toBeNull();
    expect(firstP!.classList.contains("test-placeholder")).toBe(false);

    editor.destroy();
  });
});
