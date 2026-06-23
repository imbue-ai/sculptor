import { PluginKey } from "@tiptap/pm/state";
import type { SuggestionOptions, SuggestionProps } from "@tiptap/suggestion";
import type { ForwardRefExoticComponent, RefAttributes } from "react";
import { createElement, forwardRef } from "react";

import type { EntityDataRef } from "./EntityMentionSuggestion";
import { createEntitySuggestion } from "./EntityMentionSuggestion";
import { MentionPickerList } from "./MentionPickerList";
import { createSkillSuggestion } from "./SkillSuggestion";
import { isPositionDismissed } from "./SuggestionDismissalPlugin";
import type { SuggestionListRef } from "./SuggestionListContainer";
import {
  createFileSuggestion,
  renderSuggestion,
  showSuggestionOnlyWhenTyping,
  SuggestionItem,
} from "./SuggestionUtils";

/**
 * Categories the user can drill into from the top-level `+` picker. `images`
 * has no drilled state — selecting it fires the upload dialog and closes the
 * popover. The two entity sub-categories (`repositories` / `workspaces`)
 * delegate to the same entity sub-config but pin the entity picker to a
 * specific type, skipping its internal type-picker step. Agents are reached
 * by drilling into a workspace inside the entity picker — no top-level
 * "Agents" category any more.
 */
export type MentionPickerCategory = "files" | "commands" | "repositories" | "workspaces";

type MentionPickerCategoryIcon = "files" | "commands" | "repositories" | "workspaces" | "images";

export type MentionPickerCategoryRow = SuggestionItem & {
  isCategoryRow: true;
  /** `null` for the Images row, since it has no drilled state. */
  category: MentionPickerCategory | null;
  description: string;
  /** Lucide icon name. Resolved to a component in `MentionPickerList`. */
  iconName: MentionPickerCategoryIcon;
};

/**
 * Sub-configs delegated to once the user drills into a category. We hand
 * these down to `MentionPickerList` so it can call `items()` and `command()`
 * directly — the suggestion plugin only re-runs items() on query change
 * (TipTap source: `changed = prev.query !== next.query`), so we can't rely
 * on it to refresh items when category state flips with the same query.
 */
export type MentionPickerSubConfigs = {
  fileConfig?: Omit<SuggestionOptions, "editor">;
  skillConfig?: Omit<SuggestionOptions, "editor">;
  entityConfig?: Omit<SuggestionOptions, "editor">;
};

const CATEGORY_ROWS: ReadonlyArray<{
  id: string;
  label: string;
  category: MentionPickerCategory | null;
  iconName: MentionPickerCategoryRow["iconName"];
  description: string;
}> = [
  {
    id: "__mention-picker-cat-files",
    label: "Files & folders",
    category: "files",
    iconName: "files",
    description: "Reference files and folders from within this Workspace",
  },
  {
    id: "__mention-picker-cat-commands",
    label: "Skills",
    category: "commands",
    iconName: "commands",
    description: "Run a skill or command",
  },
  {
    id: "__mention-picker-cat-workspaces",
    label: "Workspaces and Agents",
    category: "workspaces",
    iconName: "workspaces",
    description: "Reference Sculptor Workspaces and their Agents",
  },
  {
    id: "__mention-picker-cat-repositories",
    label: "Repositories",
    category: "repositories",
    iconName: "repositories",
    description: "Reference git repositories connected to Sculptor",
  },
  {
    id: "__mention-picker-cat-images",
    label: "Images",
    category: null,
    iconName: "images",
    description: "Attach images from your computer",
  },
];

const buildCategoryRows = (query: string): Array<MentionPickerCategoryRow> => {
  const lower = query.toLowerCase();
  // Match on the visible label only. Including description / iconName text
  // produced hits — e.g. "+work" matched "Files & folders" via its
  // description "Reference files and folders from within this Workspace" —
  // when users expect the search to track the names they actually see.
  return CATEGORY_ROWS.filter((row) => query === "" || row.label.toLowerCase().includes(lower)).map((row) => ({
    ...new SuggestionItem(row.id, row.label),
    isCategoryRow: true,
    category: row.category,
    description: row.description,
    iconName: row.iconName,
  }));
};

// Casting through `unknown` because `MentionPickerCategoryRow` extends a
// class (`SuggestionItem`) and lacks the `[key: string]: unknown` index
// signature the predicate's parameter type requires. The runtime check is
// correct; the assertion just placates the type narrower.
export const isMentionPickerCategoryRow = (item: {
  [key: string]: unknown;
}): item is MentionPickerCategoryRow & {
  [key: string]: unknown;
} => "isCategoryRow" in item && item.isCategoryRow === true;

type CreateMentionPickerSuggestionOptions = {
  /**
   * Provide when the editor has access to a workspace's file list. Omitting
   * this hides the "Files & folders" category — there's nothing to search.
   */
  workspaceID?: string;
  /**
   * Provide when the editor has access to a project. Required for fetching
   * skills (also used by the file picker for filesystem path-mode).
   */
  projectID?: string;
  /**
   * Provide to enable the "Sculptor entities" category. Without it, the
   * category is hidden.
   */
  entityDataRef?: EntityDataRef;
  /**
   * Fired when the user selects "Images". The popover deletes its `+query`
   * span before invoking this so the chat input is left clean and focused.
   * Provide via the harness that owns the visible image upload control —
   * the implementation typically just clicks its hidden `<input type="file">`.
   */
  onTriggerImageUpload?: () => void;
  /**
   * Character that opens this prefilter session. Defaults to `+`.
   */
  triggerChar?: string;
};

/**
 * Top-level `+` picker. Acts as a prefilter menu that drills into the same
 * sub-pickers users get from typing `@` / `/` directly.
 *
 * The plugin's `items()` only returns category rows here — `MentionPickerList`
 * owns the drilled state and fetches sub-picker items itself. This is forced
 * by TipTap's suggestion plugin: it only re-runs `items()` when the query
 * actually changes, so a state-only flip ("user drilled into Files but hasn't
 * typed yet") would otherwise leave us showing stale category rows until the
 * next keystroke.
 *
 * Step-back semantics are layered: the inner sub-list pops its own internal
 * level first (entity type-drill, file folder up), and only if it's at its
 * absolute root does control flow back to this picker, which then resets
 * the drilled category. See `SuggestionListContainer`'s `onStepBack`
 * contract for the universal Esc/Shift+Tab handling.
 */
export const createMentionPickerSuggestion = ({
  workspaceID,
  projectID,
  entityDataRef,
  onTriggerImageUpload,
  triggerChar = "+",
}: CreateMentionPickerSuggestionOptions): Omit<SuggestionOptions, "editor"> => {
  // Build the sub-configs once. The file picker's `triggerChar` is threaded
  // so any in-session text rewrites (folder drill) keep the outer prefilter
  // session alive instead of swapping to `@` mid-flow. We never register
  // these as TipTap plugins — only their items() and command() get called
  // from MentionPickerList. The pluginKey / char / render fields on the
  // returned configs are unused.
  const fileConfig =
    workspaceID && projectID ? createFileSuggestion(projectID, workspaceID, { triggerChar }) : undefined;
  const skillConfig = workspaceID
    ? createSkillSuggestion({ workspaceID })
    : projectID
      ? createSkillSuggestion({ projectID })
      : undefined;
  const entityConfig = entityDataRef ? createEntitySuggestion(entityDataRef) : undefined;
  const subConfigs: MentionPickerSubConfigs = { fileConfig, skillConfig, entityConfig };

  const isCategoryAvailable = (category: MentionPickerCategory | null): boolean => {
    if (category === null) return onTriggerImageUpload !== undefined;
    if (category === "files") return fileConfig !== undefined;
    if (category === "commands") return skillConfig !== undefined;
    if (category === "repositories" || category === "workspaces") {
      return entityConfig !== undefined;
    }
    return false;
  };

  const WrappedList: ForwardRefExoticComponent<SuggestionProps & RefAttributes<SuggestionListRef>> = forwardRef<
    SuggestionListRef,
    SuggestionProps
  >((props, ref) => createElement(MentionPickerList, { ref, subConfigs, onTriggerImageUpload, triggerChar, ...props }));
  WrappedList.displayName = `MentionPickerListWithState(${triggerChar})`;

  const pluginKey = new PluginKey(`mentionPickerPrefilter:${triggerChar}`);
  return {
    pluginKey,
    char: triggerChar,
    startOfLine: false,
    // Only fire after a space, newline, or start-of-line — typing "1+1" must
    // not open the popover. `null` (the default) would treat any non-letter
    // as a valid prefix, which is too eager.
    allowedPrefixes: [" "],

    allow: ({ state, range }): boolean => {
      const $from = state.doc.resolve(range.from);
      if ($from.parent.type.name === "codeBlock") {
        return false;
      }
      const codeMark = state.schema.marks.code;
      if (codeMark && state.doc.rangeHasMark(range.from, range.from + 1, codeMark)) {
        return false;
      }

      // Suppress reopens at trigger positions the user already dismissed.
      // See SuggestionDismissalPlugin for the lifecycle.
      if (isPositionDismissed(state, range.from)) {
        return false;
      }
      return true;
    },
    // Don't reopen on a pure cursor move into an existing `+` token (SCU-1298).
    shouldShow: showSuggestionOnlyWhenTyping(pluginKey),

    items: ({ query }): Array<MentionPickerCategoryRow> =>
      buildCategoryRows(query).filter((row) => isCategoryAvailable(row.category)),

    // MentionPickerList's `wrappedCommand` intercepts every selection and
    // dispatches either to a sub-config's command (final commits) or to its
    // own state setter (drill-in). We never reach this branch in practice;
    // it stays here only as a safety net so the option is never undefined.
    command: (): void => {},

    render: renderSuggestion(WrappedList),
  };
};
