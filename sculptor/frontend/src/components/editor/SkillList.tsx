import { Badge } from "@radix-ui/themes";
import type { SuggestionProps } from "@tiptap/suggestion";
import type { ReactElement, ReactNode } from "react";
import { forwardRef, useCallback } from "react";

import { highlightMatch } from "~/components/editor/highlightMatch";

import { badgeColorForType, badgeLabelForType, type SkillType } from "../../common/utils/skillBadge";
import styles from "./SkillList.module.scss";
import { SplitSuggestionLayout } from "./SplitSuggestionLayout";
import type { SuggestionListRef } from "./SuggestionListContainer";

const ROW_HEIGHT = 26;

const EMPTY_STATE = (
  <div className={styles.emptyRow}>
    <span className={styles.name}>No matching skills</span>
    <span className={styles.emptyHint}>
      Add in <code>.claude/skills/</code>
    </span>
  </div>
);

type SkillRowShape = {
  id: string;
  label: string;
  description?: string;
  skillType?: SkillType;
};

const SkillDetailPane = ({ item, query }: { item: SkillRowShape; query: string }): ReactElement => (
  <div className={styles.detailPane}>
    {item.skillType && (
      <Badge className={styles.badge} variant="soft" color={badgeColorForType(item.skillType)}>
        {badgeLabelForType(item.skillType)}
      </Badge>
    )}
    <span className={styles.detailTitle}>
      /{highlightMatch({ text: item.label, query, highlightClassName: styles.highlight })}
    </span>
    {item.description && <div className={styles.detailDescription}>{item.description}</div>}
  </div>
);

export type SkillListProps = SuggestionProps & {
  /**
   * Invoked when the user tries to step back from this picker. The skill
   * list has no internal hierarchy — any Shift+Tab / Escape that would
   * normally close the popover is forwarded straight to the parent so the
   * plus-prefilter picker can return to the category list.
   */
  onExitToParent?: () => void;
};

export const SkillList = forwardRef<SuggestionListRef, SkillListProps>((props, ref): ReactElement => {
  const onExitToParent = props.onExitToParent;
  const renderSkillItem = useCallback(
    (item: SkillRowShape): ReactNode => (
      <span className={styles.name}>
        /{highlightMatch({ text: item.label, query: props.query, highlightClassName: styles.highlight })}
      </span>
    ),
    [props.query],
  );

  const renderSideContent = useCallback(
    (activeItem: { id: string; label: string; [key: string]: unknown } | undefined): ReactNode => {
      if (!activeItem) return undefined;
      const skillItem = activeItem as SkillRowShape;
      return <SkillDetailPane item={skillItem} query={props.query} />;
    },
    [props.query],
  );

  const handleStepBack = useCallback((): boolean => {
    if (onExitToParent) {
      onExitToParent();
      return true;
    }
    return false;
  }, [onExitToParent]);

  return (
    <SplitSuggestionLayout
      ref={ref}
      props={props}
      rowHeight={ROW_HEIGHT}
      emptyState={EMPTY_STATE}
      renderItem={renderSkillItem}
      sideContent={renderSideContent}
      onStepBack={onExitToParent ? handleStepBack : undefined}
    />
  );
});

SkillList.displayName = "SkillList";
