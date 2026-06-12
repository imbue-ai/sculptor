import type { Editor as TipTapEditor } from "@tiptap/core";
import { Editor } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { common, createLowlight } from "lowlight";

import { CustomCodeBlockLowlight } from "./CodeBlockExtension";

const lowlight = createLowlight(common);

/**
 * Creates a minimal TipTap editor with the CustomCodeBlockLowlight extension
 * for use in unit tests. Call editor.destroy() in afterEach.
 */
export const createTestEditor = (content?: string): TipTapEditor => {
  return new Editor({
    extensions: [Document, Paragraph, Text, CustomCodeBlockLowlight.configure({ lowlight })],
    content,
  });
};

/**
 * Simulates typing text character by character, triggering input rules.
 * ProseMirror input rules only fire via handleTextInput, not bulk insertContent.
 */
export const typeText = (editor: TipTapEditor, text: string): void => {
  for (const char of text) {
    const { from, to } = editor.state.selection;
    // @ts-expect-error: handleTextInput is on DirectEditorProps, not the base EditorProps that someProp expects
    const isHandled = editor.view.someProp("handleTextInput", (f: (...args: Array<unknown>) => boolean) =>
      f(editor.view, from, to, char),
    );
    if (!isHandled) {
      editor.view.dispatch(editor.state.tr.insertText(char, from, to));
    }
  }
};

/**
 * Simulates a paste event with the given clipboard data entries.
 * Each key is a MIME type (e.g. "text/plain", "vscode-editor-data").
 * Returns true if a plugin handled the paste, false otherwise.
 */
export const simulatePaste = (editor: TipTapEditor, data: Record<string, string>): boolean => {
  const mockClipboardData = {
    getData: (type: string): string => data[type] ?? "",
    types: Object.keys(data),
    items: [] as Array<DataTransferItem>,
    files: [] as unknown as FileList,
    clearData: (): void => {},
    setData: (): void => {},
  } as unknown as DataTransfer;

  // jsdom doesn't provide ClipboardEvent, so we create a plain object mock
  const event = {
    clipboardData: mockClipboardData,
    preventDefault: (): void => {},
  } as unknown as ClipboardEvent;

  // @ts-expect-error: handlePaste is on DirectEditorProps, not the base EditorProps that someProp expects
  const isHandled = editor.view.someProp("handlePaste", (f: (...args: Array<unknown>) => boolean) =>
    f(editor.view, event, null),
  );
  return !!isHandled;
};
