import type { SuggestionProps } from "@tiptap/suggestion";
import { ChevronRight } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { forwardRef, useCallback, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { highlightMatch } from "~/common/highlightMatch";

import styles from "./EntityMentionList.module.scss";
import type { EntityMentionItem, EntityPickerRow, EntityType, TypeRowItem } from "./EntityMentionSuggestion";
import { TYPE_ICONS } from "./EntityMentionSuggestion";
import type { SuggestionListRef } from "./SuggestionListContainer";
import { SuggestionListContainer } from "./SuggestionListContainer";

const ROW_HEIGHT = 28;
const SECTION_HEADER_HEIGHT = 28;
const FIRST_SECTION_HEADER_HEIGHT = 20;

const isSectionHeader = (row: EntityPickerRow): row is Extract<EntityPickerRow, { isSectionHeader: true }> =>
  "isSectionHeader" in row && row.isSectionHeader === true;

const isTypeRow = (row: EntityPickerRow): row is TypeRowItem => "isTypeRow" in row && row.isTypeRow === true;

const isWorkspaceRow = (row: EntityPickerRow): row is EntityMentionItem =>
  !isSectionHeader(row) && !isTypeRow(row) && row.entityType === "workspace";

// A mouse click on a workspace row drills into its agents — parity with
// Tab / ArrowRight (SCU-1296). Workspace rows are the only drillable rows in
// this picker: type rows already drill on click (wrappedCommand intercepts
// them before checking the action), and every other row (repos, files,
// agents) is a leaf that should commit on click.
const isWorkspaceRowDrillable = (item: { [key: string]: unknown }): boolean =>
  isWorkspaceRow(item as unknown as EntityPickerRow);

const renderEntityItem =
  (query: string) =>
  (rawItem: { [key: string]: unknown }): ReactNode => {
    const item = rawItem as unknown as EntityPickerRow;
    if (isSectionHeader(item)) {
      return <div className={styles.sectionHeader}>{item.label}</div>;
    }

    const Icon = TYPE_ICONS[item.entityType];
    if (isTypeRow(item)) {
      return (
        <>
          <Icon className={styles.icon} aria-hidden />
          <span className={styles.name}>
            {highlightMatch({ text: item.label, query, highlightClassName: styles.highlight, element: "strong" })}
          </span>
          <span className={styles.tail}>
            <span className={styles.subtitle}>{item.description}</span>
          </span>
        </>
      );
    }
    // Workspace rows carry a trailing chevron to signal that Tab drills into
    // them — same affordance the file picker uses for folders.
    const isWorkspace = item.entityType === "workspace";
    const hasSubtitle = item.subtitle !== "";
    return (
      <>
        <Icon className={styles.icon} aria-hidden />
        <span className={styles.name}>
          {highlightMatch({
            text: item.entityDisplayName,
            query,
            highlightClassName: styles.highlight,
            element: "strong",
          })}
        </span>
        {(hasSubtitle || isWorkspace) && (
          <span className={styles.tail}>
            {hasSubtitle && <span className={styles.subtitle}>{item.subtitle}</span>}
            {isWorkspace && <ChevronRight className={styles.chevron} aria-hidden />}
          </span>
        )}
      </>
    );
  };

const EMPTY_STATE = <div className={styles.emptyState}>No results</div>;

export type EntityMentionListProps = SuggestionProps & {
  /**
   * Trigger character that anchors the suggestion session in the editor.
   * Defaults to `+` to match the prefilter picker's trigger; passing a
   * different value lets `clearQuery` keep the outer session alive when
   * the entity picker is mounted under a host that owns its own char.
   */
  triggerChar?: string;
  /**
   * Invoked when the user tries to step back past this picker's own top
   * level. Lets the prefilter picker reclaim control and return the user
   * to the category list.
   */
  onExitToParent?: () => void;
  /**
   * Pre-select an entity type and skip the type-picker step entirely. Used
   * by the prefilter picker, which exposes Repositories / Workspaces /
   * Agents as top-level categories — once the user picks one, there's
   * nothing to "drill into" inside the entity picker anymore. Step-back
   * from a pinned list goes straight to `onExitToParent`.
   */
  pinnedType?: EntityType;
};

/**
 * Entity mention picker. Three navigation states:
 *
 *   1. Top — type rows (Repositories, Workspaces) above the sectioned
 *      entity list (REPOSITORIES, WORKSPACES, AGENTS).
 *   2. Type-drilled — Tab/Enter on a type row narrows the list to that
 *      type only.
 *   3. Workspace-drilled — Tab on a workspace row narrows the list to
 *      that workspace's agents only. Enter on the same row commits the
 *      workspace as a mention. Folders-and-files semantics: Tab drills,
 *      Enter selects.
 *
 * Back out via Shift+Tab / Escape. Each Shift+Tab pops one level
 * (workspace-drill → type-drill → top). When mounted under the
 * prefilter picker, stepping back from the top level invokes
 * `onExitToParent` so the user lands on the category list.
 *
 * Each row carries enough info on its own (icon + name + secondary, mirroring
 * the file/folder picker) so the popover can stay single-column — no detail
 * pane on the right.
 */
export const EntityMentionList = forwardRef<SuggestionListRef, EntityMentionListProps>((props, ref): ReactElement => {
  const triggerChar = props.triggerChar ?? "+";
  const onExitToParent = props.onExitToParent;
  const pinnedType = props.pinnedType;
  // When pinned, the type is fixed and the local state never advances —
  // type rows are filtered out of the display so `setInternalSelectedType`
  // would never fire anyway.
  const [internalSelectedType, setInternalSelectedType] = useState<EntityType | null>(null);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const selectedType: EntityType | null = pinnedType ?? internalSelectedType;

  // Replace the current suggestion range (e.g. `+workspace`) with just the
  // trigger char so the next items() call runs with an empty query. Used
  // when drilling in or popping back so each step starts fresh.
  const clearQuery = useCallback((): void => {
    props.editor.chain().focus().deleteRange(props.range).insertContentAt(props.range.from, triggerChar).run();
  }, [props.editor, props.range, triggerChar]);

  // Intercept type-row selection and workspace drill-in before they reach the
  // suggestion config. `SuggestionListContainer.selectItem` routes Tab,
  // Enter, and click through `props.command` and tags each call with an
  // `action` — `"drillIn"` for Tab, `"select"` for Enter/click — so the
  // wrapper can branch on it the same way the file picker branches Tab on a
  // folder vs Enter on a folder.
  const wrappedCommand = useCallback(
    (item: { [key: string]: unknown }): void => {
      const row = item as unknown as EntityPickerRow & { action?: "select" | "drillIn" };
      if (isTypeRow(row)) {
        setInternalSelectedType(row.entityType);
        clearQuery();
        return;
      }

      if (isWorkspaceRow(row) && row.action === "drillIn") {
        setSelectedWorkspaceId(row.entityId);
        clearQuery();
        return;
      }
      props.command(item);
    },
    [props, clearQuery],
  );

  const rows = props.items as unknown as ReadonlyArray<EntityPickerRow>;

  // Filtering pipeline:
  //   - workspace-drilled: keep only agents whose parentId matches the
  //     drilled workspace.
  //   - type-drilled (no workspace drill): keep only entity rows of that
  //     type, dropping headers and type rows.
  //   - top: pass everything through.
  const displayRows = useMemo((): ReadonlyArray<EntityPickerRow> => {
    if (selectedWorkspaceId !== null) {
      return rows.filter(
        (row): row is EntityMentionItem =>
          !isSectionHeader(row) &&
          !isTypeRow(row) &&
          row.entityType === "agent" &&
          row.parentId === selectedWorkspaceId,
      );
    }
    if (selectedType === null) return rows;
    return rows.filter(
      (row): row is EntityPickerRow => !isSectionHeader(row) && !isTypeRow(row) && row.entityType === selectedType,
    );
  }, [rows, selectedType, selectedWorkspaceId]);

  // The inner container pulls items + command from the props object we
  // hand it. Swapping both in one memoized object keeps identity stable
  // across re-renders where neither actually changed. We deliberately rebuild
  // the spread on every render rather than memoizing — TipTap re-creates
  // `props` each time it pushes new SuggestionProps, so a memo keyed on
  // `props` would invalidate every render anyway.
  const innerProps: SuggestionProps = {
    ...props,
    items: displayRows as unknown as SuggestionProps["items"],
    command: wrappedCommand,
  };

  const renderItem = useMemo(() => renderEntityItem(props.query), [props.query]);

  // Step-back pops one drill level at a time so the user can retrace their
  // path: workspace-drill → type-drill → top → parent picker (if any).
  // Pinned mode skips the type-drill step entirely — there's nothing to
  // pop locally, so it goes straight to the parent.
  const handleStepBack = useCallback((): boolean => {
    if (selectedWorkspaceId !== null) {
      setSelectedWorkspaceId(null);
      clearQuery();
      return true;
    }

    if (pinnedType !== undefined) {
      if (onExitToParent !== undefined) {
        onExitToParent();
        return true;
      }
      return false;
    }

    if (selectedType !== null) {
      setInternalSelectedType(null);
      clearQuery();
      return true;
    }

    if (onExitToParent !== undefined) {
      onExitToParent();
      return true;
    }
    return false;
  }, [selectedWorkspaceId, pinnedType, selectedType, clearQuery, onExitToParent]);

  return (
    <div data-testid={ElementIds.ENTITY_MENTION_LIST}>
      <SuggestionListContainer
        ref={ref}
        props={innerProps}
        rowHeight={ROW_HEIGHT}
        sectionHeaderHeight={SECTION_HEADER_HEIGHT}
        firstSectionHeaderHeight={FIRST_SECTION_HEADER_HEIGHT}
        emptyState={EMPTY_STATE}
        renderItem={renderItem}
        itemTestId={ElementIds.ENTITY_MENTION_ITEM}
        onStepBack={handleStepBack}
        isRowDrillable={isWorkspaceRowDrillable}
      />
    </div>
  );
});

EntityMentionList.displayName = "EntityMentionList";
