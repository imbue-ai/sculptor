// A section's tab strip: one tab per displayed panel id (active highlighted, an
// always-visible close button, a per-panel right-click context menu, and inline
// rename for multi-instance panels), the add-panel "+", and the maximize toggle.
//
// Memoized behind primitive props and narrow per-sub-section slices so a tab drag
// only re-renders the strips of the sub-sections it touches. The tab list is the
// shallow-equal-deduped displayedPanelIdsAtom (which splices in the in-flight drag
// ghost), so an insertion-index change during a drag reorders a string array without
// rebuilding tab objects. Each tab subscribes to its OWN registry slice
// (panelDefinitionByIdAtom) so a registry rebuild on a task tick re-renders only the
// tab whose definition actually changed, not the whole strip.

import { useDraggable } from "@dnd-kit/core";
import { ContextMenu, Flex, IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Maximize2, Minimize2, Plus, X } from "lucide-react";
import type { ReactElement } from "react";
import { memo, useState } from "react";

import { ElementIds } from "~/api";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { sidebarCollapsedAtom } from "~/components/layout/sidebarAtoms.ts";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";

import { AddPanelDropdown } from "./AddPanelDropdown.tsx";
import { panelDefinitionByIdAtom } from "./registry/panelRegistry.ts";
import { isMultiInstanceKind } from "./registry/panelRegistry.ts";
import { closePanelAtom, setActivePanelAtom, splitSectionAtom } from "./sectionActions.ts";
import { activePanelIdInSubSectionAtom, sectionSplitForSectionAtom } from "./sectionAtoms.ts";
import styles from "./SectionHeader.module.scss";
import type { PanelId, SubSectionId } from "./sectionTypes.ts";
import { toSection } from "./sectionTypes.ts";
import { splitDirectionOptionsForSection } from "./splitDirection.ts";
import {
  displayedPanelIdsAtom,
  ghostPanelIdAtom,
  isReorderWithinSubSectionAtom,
  maximizedSectionAtom,
  recentlyClosedPanelIdsAtom,
} from "./transientAtoms.ts";

type PanelTabProps = {
  panelId: PanelId;
  subSection: SubSectionId;
  index: number;
  isActive: boolean;
  isGhost: boolean;
};

// One panel tab. Subscribes only to its own panel definition so a registry rebuild
// re-renders this tab only if ITS definition changed. Rename is offered for
// multi-instance panels (agent/terminal) via double-click or the context menu;
// single-instance panels cannot be renamed.
//
// The tab is a dnd-kit draggable: the whole tab is the measured node, and
// a focusable grip handle is the activator that carries the pointer/keyboard sensor
// listeners — so a plain click still activates the panel and the drag starts only
// from the handle. The floating copy is the ancestor DragOverlay; while dragging, the
// source tab dims (the live ghost placeholder is drawn in whichever section the panel
// would land in).
const PanelTabComponent = ({ panelId, subSection, index, isActive, isGhost }: PanelTabProps): ReactElement | null => {
  const definition = useAtomValue(panelDefinitionByIdAtom(panelId));
  const setActivePanel = useSetAtom(setActivePanelAtom);
  const closePanel = useSetAtom(closePanelAtom);
  const recordRecentlyClosed = useSetAtom(recentlyClosedPanelIdsAtom);
  const [isRenaming, setIsRenaming] = useState<boolean>(false);
  const section = toSection(subSection);
  const existingSplit = useAtomValue(sectionSplitForSectionAtom(section));
  const splitPanel = useSetAtom(splitSectionAtom);
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } = useDraggable({
    id: panelId,
    data: { kind: "panel", panelId, from: subSection, index },
  });

  if (definition === undefined) {
    return null;
  }

  const canRename = isMultiInstanceKind(definition.kind);

  // "Create {direction} split and move panel": one option per allowed
  // axis, offered only while the section has no split (one-split-max).
  const splitOptions = existingSplit === undefined ? splitDirectionOptionsForSection(section) : [];

  const tabClassName = [
    styles.tab,
    isActive ? styles.tabActive : "",
    isGhost ? styles.tabGhost : "",
    isDragging ? styles.tabDragging : "",
  ]
    .filter(Boolean)
    .join(" ");

  const handleActivate = (): void => {
    setActivePanel({ panelId, in: subSection });
  };

  // Double-clicking a multi-instance tab starts an inline rename, matching
  // the old agent/terminal tab gesture; the context-menu Rename item is the other entry.
  const handleDoubleClick = (): void => {
    if (canRename) {
      setIsRenaming(true);
    }
  };

  const handleClose = (event: React.MouseEvent): void => {
    event.stopPropagation();
    // Multi-instance panels (agent/terminal) delete the underlying entity — with its
    // confirmation dialog — instead of just removing the tab from the layout.
    // Static panels have no onRequestClose and just close.
    if (definition.onRequestClose !== undefined) {
      definition.onRequestClose();
    } else {
      // Single-instance panel: closing only removes it from the layout, so remember
      // it for the empty-state quick actions — it can be re-added later.
      recordRecentlyClosed(panelId);
      closePanel({ panelId });
    }
  };

  const handleRenameCommit = (newName: string): void => {
    setIsRenaming(false);
    // Persist the new name on the underlying entity (agent title / terminal label).
    // Only multi-instance panels supply onRename; static panels cannot be renamed
    // so this is a no-op for them. InlineRenameInput already trims and drops
    // empty/unchanged values before committing, so newName is a non-empty new label.
    definition.onRename?.(newName);
  };

  // The whole tab is the drag activator (no separate handle). The activator ref
  // points at the same node so the keyboard sensor only picks up when the tab
  // itself is focused — keydowns inside children (rename input, close button)
  // don't start a drag. Pointer listeners are dropped while renaming so text
  // selection inside the input can't move the panel.
  const setTabRef = (node: HTMLElement | null): void => {
    setNodeRef(node);
    setActivatorNodeRef(node);
  };

  const tabBody = (
    <div
      ref={setTabRef}
      className={tabClassName}
      {...attributes}
      {...(isRenaming ? {} : listeners)}
      role="tab"
      aria-selected={isActive}
      data-testid={`${ElementIds.PANEL_TAB}-${panelId}`}
      data-section-tab="true"
      data-panel-id={panelId}
      data-dot-status={definition.dotStatus}
      onClick={handleActivate}
      onDoubleClick={handleDoubleClick}
    >
      {isRenaming && canRename ? (
        <InlineRenameInput
          value={definition.displayName}
          onCommit={handleRenameCommit}
          onCancel={() => setIsRenaming(false)}
          isEditing
        />
      ) : (
        <span className={styles.label}>{definition.displayName}</span>
      )}
      <IconButton
        variant="ghost"
        size="1"
        color="gray"
        className={styles.closeButton}
        aria-label={`Close ${definition.displayName}`}
        data-testid={`${ElementIds.PANEL_TAB_CLOSE}-${panelId}`}
        onClick={handleClose}
      >
        <X size={12} />
      </IconButton>
    </div>
  );

  const contextActions = definition.contextMenuActions ?? [];
  const hasContextMenu = canRename || contextActions.length > 0 || splitOptions.length > 0;

  if (!hasContextMenu) {
    return tabBody;
  }

  const hasMenuAboveSplits = canRename || contextActions.length > 0;

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{tabBody}</ContextMenu.Trigger>
      <ContextMenu.Content size="1">
        {canRename && (
          <ContextMenu.Item data-testid={ElementIds.TAB_CONTEXT_MENU_RENAME} onSelect={() => setIsRenaming(true)}>
            Rename
          </ContextMenu.Item>
        )}
        {canRename && contextActions.length > 0 && <ContextMenu.Separator />}
        {contextActions.map((action) => (
          <ContextMenu.Item key={action.label} disabled={action.disabled} onSelect={() => action.action()}>
            {action.label}
          </ContextMenu.Item>
        ))}
        {hasMenuAboveSplits && splitOptions.length > 0 && <ContextMenu.Separator />}
        {splitOptions.map((option) => (
          <ContextMenu.Item
            key={option.axis}
            data-testid={`${ElementIds.SPLIT_CREATE_OPTION}-${option.axis}`}
            onSelect={() => splitPanel({ section, panelId, axis: option.axis })}
          >
            Create {option.label} split and move panel
          </ContextMenu.Item>
        ))}
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};

const PanelTab = memo(PanelTabComponent);

// The non-interactive ghost placeholder shown in the section a panel would land in
// during a CROSS-section drag. It is deliberately NOT a draggable/droppable: the real
// draggable (same panel id) is still mounted in the source section, and registering
// the id twice would confuse dnd-kit. Mirrors the tab pill shape with the ghost
// styling so the strip reserves the right footprint for the drop.
const GhostTabComponent = ({ panelId }: { panelId: PanelId }): ReactElement | null => {
  const definition = useAtomValue(panelDefinitionByIdAtom(panelId));
  if (definition === undefined) {
    return null;
  }
  return (
    <div className={`${styles.tab} ${styles.tabGhost}`} data-section-tab-ghost="true" aria-hidden="true">
      <span className={styles.label}>{definition.displayName}</span>
    </div>
  );
};

const GhostTab = memo(GhostTabComponent);

type SectionHeaderProps = { subSection: SubSectionId };

const SectionHeaderComponent = ({ subSection }: SectionHeaderProps): ReactElement => {
  const displayedPanelIds = useAtomValue(displayedPanelIdsAtom(subSection));
  const activePanelId = useAtomValue(activePanelIdInSubSectionAtom(subSection));
  const ghostPanelId = useAtomValue(ghostPanelIdAtom(subSection));
  const isReorderWithin = useAtomValue(isReorderWithinSubSectionAtom(subSection));
  const maximizedSection = useAtomValue(maximizedSectionAtom);
  const setMaximizedSection = useSetAtom(maximizedSectionAtom);
  const isSidebarCollapsed = useAtomValue(sidebarCollapsedAtom);

  const section = toSection(subSection);
  const isMaximized = maximizedSection === section;

  const handleToggleMaximize = (): void => {
    setMaximizedSection(isMaximized ? null : section);
  };

  // While maximized the workspace header is hidden, so this section header sits at the
  // very top and takes over as the top bar. Grow it to the workspace content header's
  // height (--space-7, 40px) with the tab strip centered, so maximizing doesn't change
  // the top-bar height. Non-maximized sections keep their normal (shorter) header
  // height. When the sidebar is also collapsed, reserve the left gutter for the traffic
  // lights AND the floating show-sidebar toggle (CollapsedSidebarToggle, rendered by the
  // shell), so the first tab doesn't slide under them.
  const headerStyle: React.CSSProperties | undefined = isMaximized
    ? {
        minHeight: "var(--space-7)",
        ...(isSidebarCollapsed ? { paddingLeft: `calc(${getTitleBarLeftPadding(false)} + var(--space-6))` } : {}),
      }
    : undefined;

  return (
    <Flex
      align="center"
      className={styles.header}
      style={headerStyle}
      data-maximized={isMaximized ? "true" : undefined}
      data-testid={`${ElementIds.SECTION_HEADER}-${subSection}`}
    >
      <div className={styles.tabs} data-section-tabs={subSection}>
        {displayedPanelIds.map((panelId, index) => {
          // A cross-section drag shows a non-draggable ghost here while the real
          // draggable stays in the source section; a within-section reorder keeps the
          // single instance fully draggable at its preview slot.
          if (panelId === ghostPanelId && !isReorderWithin) {
            return <GhostTab key={panelId} panelId={panelId} />;
          }
          return (
            <PanelTab
              key={panelId}
              panelId={panelId}
              subSection={subSection}
              index={index}
              isActive={panelId === activePanelId}
              isGhost={panelId === ghostPanelId}
            />
          );
        })}
      </div>
      {/* The add-panel "+" is left-aligned right after the tab strip; only the maximize
          toggle stays pinned to the far right of the header. */}
      <AddPanelDropdown
        subSection={subSection}
        tooltip="Add panel"
        trigger={
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            className={styles.headerButton}
            aria-label="Add panel"
            data-testid={`${ElementIds.SECTION_ADD_PANEL_BUTTON}-${subSection}`}
          >
            <Plus size={14} />
          </IconButton>
        }
      />
      <Flex align="center" className={styles.controls}>
        <Tooltip content={isMaximized ? "Restore section" : "Maximize section"}>
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            className={styles.headerButton}
            aria-label={isMaximized ? "Restore section" : "Maximize section"}
            data-testid={`${ElementIds.SECTION_MAXIMIZE_BUTTON}-${subSection}`}
            onClick={handleToggleMaximize}
          >
            {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </IconButton>
        </Tooltip>
      </Flex>
    </Flex>
  );
};

export const SectionHeader = memo(SectionHeaderComponent);
