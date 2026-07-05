import type { Editor as TipTapEditor } from "@tiptap/react";
import { EditorContent, useEditor } from "@tiptap/react";
import { useAtomValue } from "jotai";
import type React from "react";
import type { ReactElement } from "react";
import { useEffect, useMemo, useRef } from "react";
import { useParams } from "react-router-dom";

import { projectsArrayAtom } from "~/common/state/atoms/projects";
import { tasksArrayAtom } from "~/common/state/atoms/tasks";
import { isEntityMentionsEnabledAtom } from "~/common/state/atoms/userConfig";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces";

import { useImbueParams } from "../../common/NavigateUtils";
import { mergeClasses, optional } from "../../common/Utils.ts";
import { processAndValidateFiles, saveFiles } from "../../common/utils/fileUpload";
import type { EntityDataRef } from "../EntityMentionSuggestion";
import styles from "./Editor.module.scss";
import { hydrateEntityMentions } from "./entityMentionHydration";
import { createTipTapExtensions } from "./tipTapConfig";
import { isAnySuggestionPopoverActive } from "./utils/suggestion";

/**
 * CustomParagraph serializes empty paragraphs as "\u200B" (zero-width space).
 * When getMarkdown() returns only "\u200B", the editor is logically empty.
 * Normalize this to "" so it doesn't leak into React state and cause
 * round-trip issues when the editor is recreated via the markdown parser.
 */
const normalizeMarkdown = (md: string): string => (md === "\u200B" ? "" : md);

const isFileValidType = (item: DataTransferItem): boolean => {
  return item.kind === "file" && item.type.startsWith("image/");
};

const extractFilesFromClipboard = (items: DataTransferItemList): Array<File> => {
  const files: Array<File> = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (isFileValidType(item)) {
      const file = item.getAsFile();
      if (file) {
        files.push(file);
      }
    }
  }
  return files;
};

const handlePastedFiles = async (
  files: Array<File>,
  onFilesChange: (files: Array<string>) => void,
  onError: (error: { title: string; description?: string }) => void,
): Promise<void> => {
  try {
    const { validFiles, errors } = await processAndValidateFiles(files);

    if (errors.length > 0) {
      onError({
        title: "Paste Error",
        description: errors.join("\n"),
      });
    }

    if (validFiles.length > 0) {
      const savedFilePaths = await saveFiles(validFiles);
      if (savedFilePaths.length > 0) {
        onFilesChange(savedFilePaths);
      } else {
        onError({ title: "Failed to save pasted files" });
      }
    }
  } catch (error) {
    console.error("Error processing pasted files:", error);
    onError({ title: "Failed to process pasted files" });
  }
};

type EditorProps = {
  tagName: string;
  placeholder: string;
  value: string;
  onChange: React.Dispatch<string>;
  onKeyDown?: (event: KeyboardEvent) => boolean | void;
  wrapperClassName?: string;
  // Composed onto the scroll area's class list. Lets a host that mounts
  // the Editor in a height-constrained flex column (e.g. the Notes panel)
  // opt out of the default `max-height: 500px` cap meant for the chat
  // input, where the editor grows with content.
  scrollAreaClassName?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  footer?: ReactElement | undefined;
  onFilesChange?: (files: Array<string>) => void;
  onError?: (error: { title: string; description?: string }) => void;
  editorRef?: React.MutableRefObject<TipTapEditor | null>;
  projectID?: string;
  workspaceID?: string;
  /**
   * Forwarded to `createTipTapExtensions` so the `+` prefilter popover can
   * fire the host's image upload dialog when the user picks "Images". The
   * callback identity may change across renders; we capture it through a
   * ref so the editor isn't torn down on every parent re-render.
   */
  onTriggerImageUpload?: () => void;
};

export const Editor = ({
  tagName,
  placeholder,
  value,
  onChange,
  onKeyDown,
  wrapperClassName,
  scrollAreaClassName,
  autoFocus = true,
  disabled = false,
  footer,
  onFilesChange,
  onError,
  editorRef,
  projectID: projectIDProp,
  workspaceID: workspaceIDProp,
  onTriggerImageUpload,
}: EditorProps): ReactElement => {
  const { projectID: routeProjectID } = useImbueParams();
  const routeWorkspaceID = useParams<{ workspaceID?: string }>().workspaceID;
  const projectID = projectIDProp ?? routeProjectID;
  const workspaceID = workspaceIDProp ?? routeWorkspaceID;
  // Keep "latest ref" copies of the callback props so the editor's long-lived
  // Tiptap callbacks always invoke the current handler. These refs are read
  // only inside user-triggered Tiptap callbacks, never during render, so they
  // are synced in an effect (after commit) to satisfy the refs lint; the brief
  // post-commit window is never observed because no Tiptap callback fires during
  // render.
  const onKeyDownRef = useRef<((event: KeyboardEvent) => boolean | void) | undefined>(onKeyDown);
  const onFilesChangeRef = useRef(onFilesChange);
  const onErrorRef = useRef(onError);
  const onTriggerImageUploadRef = useRef(onTriggerImageUpload);
  // The editor is recreated only when `extensions` changes (see useEditor deps
  // below), so the `onUpdate` callback closes over whichever `onChange` was in
  // scope at editor creation. Route subsequent updates through a ref so a
  // parent that swaps in a new closure (e.g. one that captures other state)
  // doesn't end up calling a stale handler.
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onKeyDownRef.current = onKeyDown;
    onFilesChangeRef.current = onFilesChange;
    onErrorRef.current = onError;
    onTriggerImageUploadRef.current = onTriggerImageUpload;
    onChangeRef.current = onChange;
  });

  const isEntityMentionsEnabled = useAtomValue(isEntityMentionsEnabledAtom);
  const projects = useAtomValue(projectsArrayAtom);
  const workspaces = useAtomValue(workspacesArrayAtom);
  const tasks = useAtomValue(tasksArrayAtom);

  // The ref is read only inside Tiptap suggestion callbacks (user-triggered
  // events like typing `@`), never during React render. The effect below
  // keeps `.current` fresh whenever the backing atoms change; since effects
  // run after commit and before the next event-loop tick, suggestion reads
  // always see up-to-date data.
  const entityDataRef: EntityDataRef = useRef({
    repositories: projects ?? [],
    workspaces: workspaces ?? [],
    agents: tasks ?? [],
  });

  useEffect(() => {
    entityDataRef.current = {
      repositories: projects ?? [],
      workspaces: workspaces ?? [],
      agents: tasks ?? [],
    };
  }, [projects, workspaces, tasks]);

  // Memoize extensions so that createSkillSuggestion (which eagerly fetches
  // the /api/v1/skills endpoint) is not re-invoked on every render.
  const extensions = useMemo(
    () =>
      // eslint-disable-next-line react-hooks/refs -- entityDataRef is forwarded as a stable ref object; createTipTapExtensions reads .current only inside user-triggered suggestion callbacks, never during render.
      createTipTapExtensions({
        placeholder,
        editable: true,
        projectID,
        workspaceID,
        entityDataRef: isEntityMentionsEnabled ? entityDataRef : undefined,
        // Indirect through the ref so callers can pass an inline arrow
        // without busting the extensions memo on every render. Reading
        // .current is safe — the suggestion config calls this only inside
        // user-triggered command callbacks, never during construction.
        onTriggerImageUpload: () => onTriggerImageUploadRef.current?.(),
      }),
    // entityDataRef is a stable ref — not included in deps

    [placeholder, projectID, workspaceID, isEntityMentionsEnabled],
  );

  const editor = useEditor(
    {
      extensions,
      editorProps: {
        attributes: {
          class: styles.editor,
          ["data-testid"]: tagName,
          // Present only once TipTap has mounted the contenteditable, so tests
          // can gate on a stable DOM signal (`expect(...).to_have_attribute`)
          // instead of polling React fiber internals for the editor instance.
          ["data-editor-ready"]: "true",
          spellcheck: "true",
        },
        handleKeyDown: (_, event) => {
          // When a TipTap suggestion popover is visible, defer Enter to the
          // suggestion plugin's `handleKeyDown` instead of the parent's
          // `onKeyDown`. ProseMirror's `someProp` calls `editorProps` before
          // plugin props (see prosemirror-view), so a ChatInput whose
          // `send_message` keybinding is `Enter` would otherwise submit the
          // typed text before the popover could accept the highlighted
          // suggestion (SCU-1134). Scope the gate to `Enter` so any future
          // parent-handled shortcut (e.g. Ctrl+L) still fires while a popover
          // is open.
          if (event.key === "Enter" && isAnySuggestionPopoverActive()) {
            return false;
          }
          return onKeyDownRef.current?.(event) ?? false;
        },
        handlePaste: (view, event) => {
          // Only handle paste when the attach handlers are present. ChatInput
          // omits `onFilesChange` for a harness that can't accept file
          // attachments, so the paste-to-attach path is inert there. Every
          // harness that accepts attachments today (Claude and pi) also accepts
          // image input, so routing pasted images here is correct for all of
          // them. Were a future harness to accept attachments but not image
          // input, paste would still route images here while the +menu/toolbar
          // gate them — re-gate this on supportsImageInput at that point.
          if (!onFilesChangeRef.current || !onErrorRef.current) {
            return false;
          }

          const items = event.clipboardData?.items;
          if (!items) {
            return false;
          }

          const pastedFiles = extractFilesFromClipboard(items);

          if (pastedFiles.length > 0) {
            event.preventDefault();
            handlePastedFiles(pastedFiles, onFilesChangeRef.current, onErrorRef.current).catch((error) => {
              console.error("Unexpected error in handlePastedFiles:", error);
            });

            // Prevent default paste behavior
            return true;
          }

          // Let TipTap handle non-file pastes
          return false;
        },
      },
      // When value is empty, omit contentType so TipTap creates a default
      // document with an empty paragraph. The @tiptap/markdown parser produces
      // a document with zero nodes for "", which prevents the placeholder from
      // rendering until the editor gains focus.
      content: value || undefined,
      ...(value ? { contentType: "markdown" as const } : {}),
      onUpdate: ({ editor }) => {
        onChangeRef.current(normalizeMarkdown(editor.getMarkdown()));
      },
    },
    // `extensions` is memoized on the same deps that would invalidate the
    // editor, so recreating only when it changes keeps both in lockstep
    // without duplicating the dependency list.
    [extensions],
  );

  // Expose the TipTap editor instance to parent components via ref, and stash it
  // on its own contenteditable DOM node as `__tiptapEditor`. The DOM handle lets
  // integration tests reach the live editor without walking React fiber
  // internals (whose private field names break across React/TipTap upgrades).
  // It is attached per-node — never a global — so multiple editors (e.g. several
  // agents on screen) each carry their own handle. Both are nulled/removed on
  // teardown so a detaching editor (after an agent/workspace switch) stops
  // advertising a destroyed instance.
  //
  // Stashing the editor on its own DOM node is a deliberate test-access side
  // effect; the immutability lint flags it (and the effect) because `dom` is
  // derived from the hook-returned `editor`, but it cannot tell this apart from
  // mutating render output — hence the scoped disable below.
  /* eslint-disable react-hooks/immutability */
  useEffect(() => {
    if (editorRef) editorRef.current = editor;
    if (!editor) {
      return undefined;
    }
    const dom = editor.view.dom as HTMLElement & { __tiptapEditor?: unknown };
    dom.__tiptapEditor = editor;
    return (): void => {
      if (editorRef) editorRef.current = null;
      delete dom.__tiptapEditor;
    };
  }, [editor, editorRef]);
  /* eslint-enable react-hooks/immutability */

  // Hydrate `+[type:id|display_name]` text into entity-mention nodes once the
  // editor exists. The editor is initialized with `content: value` and
  // markdown contentType, but the markdown parser leaves the compact `+[…]`
  // token as literal text — and the value-change effect below skips the
  // re-hydration call when the markdown round-trips identical (the
  // restored-draft case). Hydrating here covers the initial mount.
  useEffect(() => {
    if (!editor) return;
    hydrateEntityMentions(editor);
  }, [editor]);

  // Handle autoFocus
  useEffect(() => {
    if (autoFocus && editor) {
      editor.commands.focus("end");
    }
  }, [autoFocus, editor]);

  useEffect(() => {
    if (editor) {
      const currentMarkdown = normalizeMarkdown(editor.getMarkdown());

      // Only update if the content is different from the incoming value
      if (value !== currentMarkdown) {
        if (value) {
          editor.commands.setContent(value, { contentType: "markdown" });
          // Re-hydrate `+[type:id|display_name]` text into entity-mention
          // nodes. The markdown parser leaves the token as literal text,
          // so without this an entity-mention draft restored from
          // localStorage (e.g. after navigating between agents) would
          // render as raw `+[…]` text instead of a styled chip.
          hydrateEntityMentions(editor);
        } else {
          editor.commands.clearContent();
        }
      }
    }
  }, [value, editor]);

  // Set initial editable state and update when disabled changes
  useEffect(() => {
    if (editor && editor.isEditable !== !disabled) {
      editor.setEditable(!disabled);
    }
  }, [disabled, editor]);

  return (
    <div className={mergeClasses(wrapperClassName ?? styles.editorWrapper, optional(disabled, styles.disabled))}>
      <div className={mergeClasses(styles.scrollArea, scrollAreaClassName)}>
        <EditorContent editor={editor} />
      </div>
      {footer && <div className={styles.footer}>{footer}</div>}
    </div>
  );
};
