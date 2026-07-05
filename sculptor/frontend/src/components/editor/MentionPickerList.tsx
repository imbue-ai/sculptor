import type { SuggestionProps } from "@tiptap/suggestion";
import { AtSign, FolderGit2, ImageIcon, Layers, type LucideIcon, SquareSlash } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { forwardRef, useCallback, useEffect, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { highlightMatch } from "~/components/editor/highlightMatch";

import type { EntityType } from "../EntityMentionSuggestion";
import { EntityMentionList } from "./EntityMentionList";
import { MentionList } from "./MentionList";
import styles from "./MentionPickerList.module.scss";
import type {
  MentionPickerCategory,
  MentionPickerCategoryRow,
  MentionPickerSubConfigs,
} from "./mentionPickerSuggestion";
import { isMentionPickerCategoryRow } from "./mentionPickerSuggestion";
import { SkillList } from "./SkillList";
import { SplitSuggestionLayout } from "./SplitSuggestionLayout";
import type { SuggestionListRef } from "./SuggestionListContainer";

const ROW_HEIGHT = 26;

// Files use the `@`-trigger glyph and skills use the `/`-trigger glyph so
// the `+` category rows visually echo the trigger char a power-user would
// type to reach the same picker directly.
const ICON_FOR_NAME: Record<MentionPickerCategoryRow["iconName"], LucideIcon> = {
  files: AtSign,
  commands: SquareSlash,
  repositories: FolderGit2,
  workspaces: Layers,
  images: ImageIcon,
};

const EMPTY_STATE = <div className={styles.emptyState}>No matching categories</div>;

// Maps a category to the entity type the entity picker should pin.
// `null` means the category isn't backed by the entity picker. The
// "workspaces" category pins to `workspace` and lets the user reach agents
// by drilling into a specific workspace row — no separate "agents"
// category exists.
const ENTITY_TYPE_FOR_CATEGORY: Record<MentionPickerCategory, EntityType | null> = {
  files: null,
  commands: null,
  repositories: "repository",
  workspaces: "workspace",
};

type MentionPickerListProps = SuggestionProps & {
  subConfigs: MentionPickerSubConfigs;
  onTriggerImageUpload?: () => void;
  /**
   * Trigger char that opened this prefilter session. The picker's plugin
   * is keyed by trigger char, so any in-session text rewrites — drill-in
   * clearQuery, back-to-categories — have to preserve whichever char the
   * user actually typed.
   */
  triggerChar: string;
};

const subConfigForCategory = (
  category: MentionPickerCategory,
  subConfigs: MentionPickerSubConfigs,
): {
  items?: NonNullable<MentionPickerListProps["subConfigs"]["fileConfig"]>["items"];
  command?: NonNullable<MentionPickerListProps["subConfigs"]["fileConfig"]>["command"];
} => {
  if (category === "files") return { items: subConfigs.fileConfig?.items, command: subConfigs.fileConfig?.command };
  if (category === "commands")
    return { items: subConfigs.skillConfig?.items, command: subConfigs.skillConfig?.command };
  // Both entity sub-categories (repositories / workspaces) share the same
  // sub-config — the per-type filter is applied inside `EntityMentionList`
  // via `pinnedType`.
  return { items: subConfigs.entityConfig?.items, command: subConfigs.entityConfig?.command };
};

/**
 * Top-level renderer for the `+` prefilter picker. When no category is
 * selected, it renders the category rows with `SplitSuggestionLayout`
 * (matching the `/`-skill picker's layout — one row of label per category,
 * details in the right pane). Once the user drills into a category, it
 * forwards to the matching sub-list and passes the active trigger char so
 * any in-session text rewrites preserve the outer prefilter session.
 *
 * Drilled state lives in this component's `useState`. We can't lean on
 * TipTap's suggestion plugin to refresh items() after a state-only flip
 * (the plugin only re-runs items() when the query string actually
 * changes), so MentionPickerList fetches sub-picker items itself in a
 * `useEffect` — keyed on `(category, query)` — and overrides `props.items`
 * for the drilled sub-list. Final-item commits are delegated to the sub-
 * config's `command` directly; category-row Tab/Enter just flips local
 * state and clears the editor query, so the suggestion session stays open
 * and `pickerStateRef`-style tear-down is sidestepped entirely.
 */
export const MentionPickerList = forwardRef<SuggestionListRef, MentionPickerListProps>(
  ({ subConfigs, onTriggerImageUpload, triggerChar, ...suggestionProps }, ref): ReactElement => {
    const [category, setCategory] = useState<MentionPickerCategory | null>(null);
    const [drilledItems, setDrilledItems] = useState<Array<unknown>>([]);

    const goBackToCategoryList = useCallback((): void => {
      setCategory(null);
      // Replace `<trigger>query` with just `<trigger>` so the next
      // category-list pass shows an empty filter. The query the user typed
      // inside the sub-picker (a file name, an entity label) is rarely a
      // meaningful category filter, so we drop it on the way back up.
      suggestionProps.editor
        .chain()
        .focus()
        .deleteRange(suggestionProps.range)
        .insertContentAt(suggestionProps.range.from, triggerChar)
        .run();
    }, [suggestionProps.editor, suggestionProps.range, triggerChar]);

    // Re-fetch items whenever the drilled category or the user's query
    // changes. Cancellation guards against stale async resolutions when
    // the user types fast or backs out mid-flight.
    useEffect(() => {
      if (category === null) {
        setDrilledItems([]);
        return;
      }
      const subConfig = subConfigForCategory(category, subConfigs);
      if (!subConfig.items) {
        setDrilledItems([]);
        return;
      }
      let isCancelled = false;
      Promise.resolve(subConfig.items({ query: suggestionProps.query, editor: suggestionProps.editor })).then(
        (items) => {
          if (!isCancelled) setDrilledItems(items as Array<unknown>);
        },
      );
      return (): void => {
        isCancelled = true;
      };
    }, [category, suggestionProps.query, suggestionProps.editor, subConfigs]);

    const wrappedCommand = useCallback(
      (item: { [key: string]: unknown }): void => {
        if (isMentionPickerCategoryRow(item)) {
          if (item.category === null) {
            // Images: terminal. Strip the `+` text and fire the upload dialog;
            // the editor regains focus naturally. The row is only present when
            // the harness accepts image input (filtered from `innerProps`
            // otherwise).
            suggestionProps.editor.chain().focus().deleteRange(suggestionProps.range).run();
            onTriggerImageUpload?.();
            return;
          }
          // Drill-in. Flip React state and clear whatever the user typed
          // to filter the category list — that text was meaningful as a
          // category filter ("com" → Commands) but rarely matches the
          // commands the user actually wants to find. Replacing
          // `<trigger>query` with just `<trigger>` resets the suggestion
          // query to empty; useEffect picks that up and refetches the
          // drilled items.
          setCategory(item.category);
          suggestionProps.editor
            .chain()
            .focus()
            .deleteRange(suggestionProps.range)
            .insertContentAt(suggestionProps.range.from, triggerChar)
            .run();
          return;
        }
        // Final commit inside a drilled category. Delegate to the sub-
        // config's command directly; that command inserts a mention node
        // (terminating the session) or rewrites the trigger text for a
        // folder-drill (continuing the session). Either way, bypassing
        // `suggestionProps.command` is safe — it would just call our
        // MentionPickerSuggestion config's `command` which is a no-op stub.
        if (category === null) return;
        const subConfig = subConfigForCategory(category, subConfigs);
        subConfig.command?.({
          editor: suggestionProps.editor,
          range: suggestionProps.range,
          props: item,
        });
      },
      [category, subConfigs, suggestionProps.editor, suggestionProps.range, onTriggerImageUpload, triggerChar],
    );

    const innerProps = useMemo((): SuggestionProps => {
      if (category !== null) {
        return { ...suggestionProps, items: drilledItems, command: wrappedCommand };
      }
      // The Images category (the row whose `category` is `null`) fires the
      // image-upload picker. When the harness can't accept image input,
      // ChatInput passes no `onTriggerImageUpload`, so the row is filtered out
      // of the list rather than left as a dead entry.
      const items = onTriggerImageUpload
        ? suggestionProps.items
        : suggestionProps.items.filter((item) => !(isMentionPickerCategoryRow(item) && item.category === null));
      return { ...suggestionProps, items, command: wrappedCommand };
    }, [suggestionProps, drilledItems, wrappedCommand, category, onTriggerImageUpload]);

    const renderCategoryRow = useCallback(
      (rawItem: { id: string; label: string; [key: string]: unknown }): ReactNode => {
        if (!isMentionPickerCategoryRow(rawItem)) return null;
        const Icon = ICON_FOR_NAME[rawItem.iconName];
        // Fragment + sibling spans (mirrors MentionList) so the row's flex
        // container puts gap between icon and label only — NOT between each
        // span `highlightMatch` returns. Wrapping the label in a flex
        // container would space out the matched/unmatched substrings.
        return (
          <>
            <Icon className={styles.rowIcon} size={14} aria-hidden />
            <span className={styles.name}>
              {highlightMatch({
                text: rawItem.label,
                query: suggestionProps.query,
                highlightClassName: styles.highlight,
              })}
            </span>
          </>
        );
      },
      [suggestionProps.query],
    );

    // The right-pane detail view is purely orientational — it explains what
    // each category contains for a user who hasn't picked one yet. As soon
    // as the user starts typing they're searching, not browsing, so we
    // collapse to a single-column list (returning `null` here makes the
    // shared container drop `.suggestionListSplit` and its min-width /
    // min-height floors) — a tighter, faster search experience.
    const renderCategoryDetail = useCallback(
      (rawItem: { id: string; label: string; [key: string]: unknown } | undefined): ReactNode => {
        if (suggestionProps.query !== "") return null;
        if (!rawItem || !isMentionPickerCategoryRow(rawItem)) return null;
        // The left-pane row already shows the icon + label, so the right
        // pane only repeats the description — keeps the popover lean.
        return (
          <div className={styles.detailPane}>
            <div className={styles.detailDescription}>{rawItem.description}</div>
          </div>
        );
      },
      [suggestionProps.query],
    );

    if (category === "files") {
      return <MentionList ref={ref} triggerChar={triggerChar} onExitToParent={goBackToCategoryList} {...innerProps} />;
    }

    if (category === "commands") {
      return <SkillList ref={ref} onExitToParent={goBackToCategoryList} {...innerProps} />;
    }

    const pinnedEntityType = category !== null ? ENTITY_TYPE_FOR_CATEGORY[category] : null;
    if (pinnedEntityType !== null) {
      return (
        <EntityMentionList
          ref={ref}
          triggerChar={triggerChar}
          pinnedType={pinnedEntityType}
          onExitToParent={goBackToCategoryList}
          {...innerProps}
        />
      );
    }

    return (
      <SplitSuggestionLayout
        ref={ref}
        props={innerProps}
        rowHeight={ROW_HEIGHT}
        emptyState={EMPTY_STATE}
        renderItem={renderCategoryRow}
        itemTestId={ElementIds.MENTION_PICKER_CATEGORY_ITEM}
        sideContent={renderCategoryDetail}
      />
    );
  },
);

MentionPickerList.displayName = "MentionPickerList";
