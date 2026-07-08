import type { Editor, NodeViewProps } from "@tiptap/core";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import { NodeSelection } from "@tiptap/pm/state";
import { NodeViewWrapper } from "@tiptap/react";
import type { ReactElement } from "react";
import { useCallback, useSyncExternalStore } from "react";

import { disambiguateFileNames } from "~/pages/workspace/components/chat-alpha/chipRowUtils.ts";

import type { EntityType } from "./EntityMentionSuggestion";
import { MentionChip } from "./MentionChip";
import type { SkillType } from "./skillBadge";

const WRAPPER_PROPS = { as: "span" } as const;

const stripFileIdToPath = (id: string): string => {
  const noAt = id.startsWith("@") ? id.slice(1) : id;
  return noAt.endsWith("/") ? noAt.slice(0, -1) : noAt;
};

// Cache the file-disambiguation map per ProseMirror doc. Docs are immutable
// (every edit produces a new Node), so doc identity is a perfect cache key —
// once we walk a doc to build its disambiguation map, every chip living in
// that doc reads its slot in O(1) instead of re-walking the whole doc itself.
const disambiguationCache = new WeakMap<ProseMirrorNode, Map<string, string>>();

const getDisambiguationForDoc = (doc: ProseMirrorNode): Map<string, string> => {
  const cached = disambiguationCache.get(doc);
  if (cached) return cached;
  const paths: Array<string> = [];
  doc.descendants((n) => {
    if (n.type.name !== "mention" || n.attrs.entityType) return;
    const otherId = n.attrs.id;
    if (typeof otherId !== "string" || otherId.startsWith("/")) return;
    paths.push(stripFileIdToPath(otherId));
  });
  const map = disambiguateFileNames(paths);
  disambiguationCache.set(doc, map);
  return map;
};

// Resolve the visible label for a file/folder chip when sibling chips in the
// same input share a basename. Returns `null` when the chip isn't a file/folder
// mention or when no override is needed — `FileMentionChip` falls back to the
// bare basename.
const computeFileChipDisplayLabel = (editor: Editor, id: unknown): string | null => {
  if (typeof id !== "string" || id.startsWith("/")) return null;
  const myPath = stripFileIdToPath(id);
  return getDisambiguationForDoc(editor.state.doc).get(myPath) ?? null;
};

export const MentionNodeView = ({ node, editor, getPos }: NodeViewProps): ReactElement => {
  // Tiptap's `selected` prop only toggles when this specific chip enters or
  // leaves the selection range — so we can't rely on it mid-drag for chips
  // the user hasn't covered yet, or for suppressing hover on chips outside
  // the range. Subscribe directly to `selectionUpdate` so every chip sees
  // every selection change.
  const subscribe = useCallback(
    (onChange: () => void): (() => void) => {
      editor.on("selectionUpdate", onChange);
      return (): void => {
        editor.off("selectionUpdate", onChange);
      };
    },
    [editor],
  );
  const isSelectionEmpty = useSyncExternalStore(subscribe, () => editor.state.selection.empty);
  const isNodeSelected = useSyncExternalStore(subscribe, () => {
    const sel = editor.state.selection;
    const pos = typeof getPos === "function" ? getPos() : undefined;
    return sel instanceof NodeSelection && sel.from === pos;
  });

  // Recompute the disambiguated label whenever the doc changes (chip added,
  // removed, or restored from a draft). Strings compare with Object.is, so
  // recomputing into the same value during repeated getSnapshot calls does
  // not trigger spurious re-renders.
  const subscribeToDoc = useCallback(
    (onChange: () => void): (() => void) => {
      editor.on("update", onChange);
      return (): void => {
        editor.off("update", onChange);
      };
    },
    [editor],
  );
  const fileDisplayLabel = useSyncExternalStore(subscribeToDoc, () =>
    computeFileChipDisplayLabel(editor, node.attrs.id),
  );

  // Pin the popover open only for an exact NodeSelection on this chip
  // (arrow-key chip select or a click on the chip).
  // Suppress hover whenever the editor has any non-empty selection that
  // isn't this chip's NodeSelection — covers Cmd+A, drag-select, and
  // chips the drag hasn't fully enclosed yet.
  const sharedProps = {
    wrapperElement: NodeViewWrapper,
    wrapperProps: WRAPPER_PROPS,
    selected: isNodeSelected,
    suppressHover: !isSelectionEmpty && !isNodeSelected,
  };

  // Dispatch by which attribute set the node carries. Entity chips are
  // identified by a non-null `entityType`; spotlight chips carry
  // `spotlightFile`; otherwise fall through to the file/skill chip, whose
  // variant is inferred from the leading `/` of `id`.
  const spotlightFile = node.attrs.spotlightFile as string | null | undefined;
  if (spotlightFile) {
    return (
      <MentionChip
        kind="spotlight"
        file={spotlightFile}
        lineStart={Number(node.attrs.spotlightLineStart ?? 0)}
        lineEnd={Number(node.attrs.spotlightLineEnd ?? 0)}
        side={(node.attrs.spotlightSide as "old" | "new" | null) ?? null}
        {...sharedProps}
      />
    );
  }

  if (node.attrs.entityType) {
    return (
      <MentionChip
        kind="entity"
        entityType={node.attrs.entityType as EntityType}
        entityId={String(node.attrs.entityId ?? "")}
        entityDisplayName={String(node.attrs.entityDisplayName ?? "")}
        {...sharedProps}
      />
    );
  }

  return (
    <MentionChip
      id={node.attrs.id as string}
      displayLabel={fileDisplayLabel}
      skillDescription={node.attrs.skillDescription as string | null}
      skillType={node.attrs.skillType as SkillType | null}
      {...sharedProps}
    />
  );
};
