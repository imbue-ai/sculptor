import type { SuggestionProps } from "@tiptap/suggestion";
import { Folder } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { forwardRef, useCallback } from "react";

import { ElementIds } from "~/api";
import { highlightMatch } from "~/common/highlightMatch";
import { getFileIcon } from "~/pages/workspace/panels/fileBrowser/fileIcons";

import styles from "./MentionList.module.scss";
import type { SuggestionListRef } from "./SuggestionListContainer";
import { SuggestionListContainer } from "./SuggestionListContainer";
import { navigateUpPathMode } from "./SuggestionUtils";

const ROW_HEIGHT = 26;

// A mouse click on a folder row drills into it — parity with Tab / ArrowRight
// (SCU-1415, follow-up to SCU-1296). Folder labels end in "/"; every other row
// is a file leaf that commits on click. createFileSuggestion already drills
// when the action is "drillIn", so a click on a folder now opens its contents.
const isFolderRow = (item: { label: string; [key: string]: unknown }): boolean => item.label.endsWith("/");

type MentionListProps = SuggestionProps & {
  /**
   * Trigger character that opened this suggestion session. Defaults to `@`
   * when the file picker is mounted directly under its own trigger; plus-
   * prefilter callers pass `+` so folder-drill and path-up operations
   * preserve the outer trigger in the editor instead of swapping it.
   */
  triggerChar?: string;
  /**
   * Invoked when the user tries to step back past this picker's own root
   * (via Shift+Tab or Escape). Lets the plus-prefilter picker reclaim
   * control and return the user to the category list.
   */
  onExitToParent?: () => void;
};

export const MentionList = forwardRef<SuggestionListRef, MentionListProps>((props, ref): ReactElement => {
  const triggerChar = props.triggerChar ?? "@";
  const onExitToParent = props.onExitToParent;
  const renderMentionItem = useCallback(
    (item: { id: string; label: string; parentPath?: string }): ReactNode => {
      const isDirectory = item.label.endsWith("/");
      const displayName = isDirectory ? item.label.slice(0, -1) : item.label;
      const Icon = isDirectory ? Folder : getFileIcon(item.label);
      return (
        <>
          <Icon className={styles.icon} />
          <span className={styles.name}>
            {highlightMatch({ text: displayName, query: props.query, highlightClassName: styles.highlight })}
          </span>
          {item.parentPath && <span className={styles.parentPath}>{item.parentPath}</span>}
        </>
      );
    },
    [props.query],
  );

  // Try to walk up one folder level first. When already at the fuzzy root
  // there is no further level for *this* list to pop — if we're running
  // under the plus-prefilter picker, hand control to its `onExitToParent` so
  // the user backs out to the category list.
  const handleStepBack = useCallback((): boolean => {
    if (navigateUpPathMode(props, triggerChar)) return true;
    if (onExitToParent) {
      onExitToParent();
      return true;
    }
    return false;
  }, [props, triggerChar, onExitToParent]);

  return (
    <SuggestionListContainer
      ref={ref}
      props={props}
      rowHeight={ROW_HEIGHT}
      emptyState={
        <span className={`${styles.name} ${styles.emptyText}`}>
          {props.query ? "No matching files or folders" : "Type to search files"}
        </span>
      }
      renderItem={renderMentionItem}
      itemTestId={ElementIds.FILE_MENTION_SUGGESTION_ITEM}
      onStepBack={handleStepBack}
      isRowDrillable={isFolderRow}
    />
  );
});

MentionList.displayName = "MentionList";
