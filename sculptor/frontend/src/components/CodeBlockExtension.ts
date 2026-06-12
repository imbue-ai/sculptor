import { InputRule } from "@tiptap/core";
import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import { Fragment, Slice } from "@tiptap/pm/model";
import { Plugin, PluginKey, TextSelection } from "@tiptap/pm/state";
import { canJoin } from "@tiptap/pm/transform";

/**
 * Strips the minimum common leading whitespace from all non-empty lines.
 * This normalizes indentation when code is copied from inside functions/classes.
 */
export const dedentText = (text: string): string => {
  const lines = text.split("\n");
  const nonEmptyLines = lines.filter((line) => line.trim().length > 0);

  if (nonEmptyLines.length === 0) {
    return text;
  }

  const minIndent = Math.min(
    ...nonEmptyLines.map((line) => {
      const match = line.match(/^(\s*)/);
      return match ? match[0].length : 0;
    }),
  );

  if (minIndent === 0) {
    return text;
  }

  return lines.map((line) => line.slice(minIndent)).join("\n");
};

/**
 * Custom CodeBlockLowlight extension with Slack-like behavior:
 * - Typing ``` creates a code block immediately (no space/enter needed)
 * - Text after ``` goes into the code block
 * - Text before ``` (middle of line) stays as a paragraph
 * - Consecutive code blocks are merged
 * - Pasted code is automatically dedented
 */
export const CustomCodeBlockLowlight = CodeBlockLowlight.extend({
  addInputRules() {
    return [
      new InputRule({
        find: /```$/,
        handler: ({ state, range }): void => {
          // Don't create nested code blocks
          if (this.editor.isActive(this.type.name)) {
            return;
          }

          const { tr } = state;
          const $from = state.doc.resolve(range.from);
          const textblockStart = $from.start();
          const textblockEnd = $from.end();

          // Text before the ``` in the current textblock
          const textBefore = state.doc.textBetween(textblockStart, range.from);
          // Text after the cursor (after ```) in the current textblock
          const textAfter = range.to < textblockEnd ? state.doc.textBetween(range.to, textblockEnd) : "";

          if (textBefore.length > 0) {
            // ``` in the middle of a line: keep text before as paragraph, create code block with text after
            // Delete from ``` to end of textblock
            tr.delete(range.from, textblockEnd);

            // Insert a new code block after the current paragraph
            const codeBlockContent = textAfter.length > 0 ? state.schema.text(textAfter) : undefined;
            const codeBlock = this.type.create({}, codeBlockContent ? [codeBlockContent] : undefined);
            const insertPos = tr.mapping.map(range.from);
            const $insertPos = tr.doc.resolve(insertPos);
            const afterParent = $insertPos.after($insertPos.depth);
            tr.insert(afterParent, codeBlock);

            // Place cursor inside the code block
            const codeBlockStartPos = afterParent + 1;
            tr.setSelection(TextSelection.create(tr.doc, codeBlockStartPos + textAfter.length));
          } else {
            // ``` at start of line: convert the textblock to a code block
            // Delete the ``` trigger
            tr.delete(range.from, range.to);

            // Set the block type to code block
            const mappedFrom = tr.mapping.map(range.from);
            tr.setBlockType(mappedFrom, mappedFrom, this.type);

            // Place cursor at end of any remaining text
            const $newPos = tr.doc.resolve(mappedFrom);
            const endOfBlock = $newPos.end();
            tr.setSelection(TextSelection.create(tr.doc, endOfBlock));
          }

          // Merge with adjacent code block above (only if it's also a code block)
          const $codeBlock = tr.doc.resolve(tr.selection.from);
          const codeBlockPos = $codeBlock.before($codeBlock.depth);
          if (codeBlockPos > 0) {
            const $joinPos = tr.doc.resolve(codeBlockPos);
            if ($joinPos.nodeBefore?.type === this.type && canJoin(tr.doc, codeBlockPos)) {
              // Insert a newline at the end of the upper code block before merging
              const upperBlockEnd = codeBlockPos - 1;
              tr.insertText("\n", upperBlockEnd);
              // Re-resolve the join position after the newline insertion
              const mappedJoinPos = tr.mapping.map(codeBlockPos);
              tr.join(mappedJoinPos);
            }
          }
        },
      }),
    ];
  },

  addProseMirrorPlugins() {
    // Our custom paste handlers are listed first so they take priority over the
    // parent's default VS Code handler (ProseMirror stops at the first handler
    // that returns true).
    const parentPlugins = this.parent?.() ?? [];

    return [
      new Plugin({
        key: new PluginKey("codeBlockVSCodeHandlerCustom"),
        props: {
          handlePaste: (view, event): boolean => {
            if (!event.clipboardData) {
              return false;
            }

            // Don't create a new code block within code blocks
            if (this.editor.isActive(this.type.name)) {
              return false;
            }

            const text = event.clipboardData.getData("text/plain");
            const vscode = event.clipboardData.getData("vscode-editor-data");
            const vscodeData = vscode ? JSON.parse(vscode) : undefined;
            const language = vscodeData?.mode as string | undefined;

            if (!text || !language) {
              return false;
            }

            const { tr, schema } = view.state;

            // Dedent and normalize line endings
            const dedented = dedentText(text.replace(/\r\n?/g, "\n"));
            const textNode = schema.text(dedented);

            tr.replaceSelectionWith(this.type.create({ language }, textNode));

            if (tr.selection.$from.parent.type !== this.type) {
              tr.setSelection(TextSelection.near(tr.doc.resolve(Math.max(0, tr.selection.from - 2))));
            }

            tr.setMeta("paste", true);
            view.dispatch(tr);

            return true;
          },
        },
      }),
      // Paste handler for pasting into existing code blocks — dedent the text
      new Plugin({
        key: new PluginKey("codeBlockPasteDedent"),
        props: {
          handlePaste: (view, event): boolean => {
            if (!event.clipboardData) {
              return false;
            }

            // Only handle paste when inside a code block
            if (!this.editor.isActive(this.type.name)) {
              return false;
            }

            // Skip VS Code pastes (handled by the other plugin)
            const vscode = event.clipboardData.getData("vscode-editor-data");
            if (vscode) {
              return false;
            }

            const text = event.clipboardData.getData("text/plain");
            if (!text) {
              return false;
            }

            const dedented = dedentText(text.replace(/\r\n?/g, "\n"));

            // If no change, let default handling proceed
            if (dedented === text) {
              return false;
            }

            const { tr, schema } = view.state;
            const textNode = schema.text(dedented);
            tr.replaceSelection(new Slice(Fragment.from(textNode), 0, 0));
            tr.setMeta("paste", true);
            view.dispatch(tr);

            return true;
          },
        },
      }),
      ...parentPlugins,
    ];
  },
});
