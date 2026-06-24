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

import { ContextMenu, Flex, IconButton } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Maximize2, Minimize2, Plus, X } from "lucide-react";
import type { ReactElement } from "react";
import { memo, useState } from "react";

import { ElementIds } from "~/api";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";

import { AddPanelDropdown } from "./AddPanelDropdown.tsx";
import { panelDefinitionByIdAtom } from "./registry/panelRegistry.ts";
import { isMultiInstanceKind } from "./registry/panelRegistry.ts";
import { closePanelAtom, setActivePanelAtom } from "./sectionActions.ts";
import { activePanelIdInSubSectionAtom } from "./sectionAtoms.ts";
import styles from "./SectionHeader.module.scss";
import type { PanelId, SubSectionId } from "./sectionTypes.ts";
import { toSection } from "./sectionTypes.ts";
import {
  displayedPanelIdsAtom,
  ghostPanelIdAtom,
  maximizedSectionAtom,
  recentlyClosedPanelIdsAtom,
} from "./transientAtoms.ts";

type PanelTabProps = {
  panelId: PanelId;
  subSection: SubSectionId;
  isActive: boolean;
  isGhost: boolean;
};

// One panel tab. Subscribes only to its own panel definition so a registry rebuild
// re-renders this tab only if ITS definition changed. Rename is offered for
// multi-instance panels (agent/terminal) via the context menu; single-instance
// panels cannot be renamed (PANEL-11).
const PanelTabComponent = ({ panelId, subSection, isActive, isGhost }: PanelTabProps): ReactElement | null => {
  const definition = useAtomValue(panelDefinitionByIdAtom(panelId));
  const setActivePanel = useSetAtom(setActivePanelAtom);
  const closePanel = useSetAtom(closePanelAtom);
  const recordRecentlyClosed = useSetAtom(recentlyClosedPanelIdsAtom);
  const [isRenaming, setIsRenaming] = useState<boolean>(false);

  if (definition === undefined) {
    return null;
  }

  const canRename = isMultiInstanceKind(definition.kind);
  const Icon = definition.icon;

  const tabClassName = [styles.tab, isActive ? styles.tabActive : "", isGhost ? styles.tabGhost : ""]
    .filter(Boolean)
    .join(" ");

  const handleActivate = (): void => {
    setActivePanel({ panelId, in: subSection });
  };

  const handleClose = (event: React.MouseEvent): void => {
    event.stopPropagation();
    // Multi-instance panels (agent/terminal) delete the underlying entity — with its
    // confirmation dialog — instead of just removing the tab from the layout
    // (AGENT-04/08). Static panels have no onRequestClose and just close.
    if (definition.onRequestClose !== undefined) {
      definition.onRequestClose();
    } else {
      // Single-instance panel: closing only removes it from the layout, so remember
      // it for the empty-state quick actions (SEC-19) — it can be re-added later.
      recordRecentlyClosed(panelId);
      closePanel({ panelId });
    }
  };

  const handleRenameCommit = (newName: string): void => {
    setIsRenaming(false);
    // The rename mutation (renaming the underlying agent/terminal) is wired to the
    // data layer in a later task; this affordance is offered only for multi-instance
    // panels here. newName is the committed value for that wiring.
    void newName;
  };

  const tabBody = (
    <div
      className={tabClassName}
      role="tab"
      aria-selected={isActive}
      data-testid={`${ElementIds.PANEL_TAB}-${panelId}`}
      data-section-tab="true"
      onClick={handleActivate}
    >
      <span className={styles.icon}>
        {/* Multi-instance panels carry a per-instance tabIcon (the agent status dot —
            read/unread + running/waiting, AGENT-07); static panels fall back to their
            lucide kind icon. */}
        {definition.tabIcon ?? <Icon size={14} />}
      </span>
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
  const hasContextMenu = canRename || contextActions.length > 0;

  if (!hasContextMenu) {
    return tabBody;
  }

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
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};

const PanelTab = memo(PanelTabComponent);

type SectionHeaderProps = { subSection: SubSectionId };

const SectionHeaderComponent = ({ subSection }: SectionHeaderProps): ReactElement => {
  const displayedPanelIds = useAtomValue(displayedPanelIdsAtom(subSection));
  const activePanelId = useAtomValue(activePanelIdInSubSectionAtom(subSection));
  const ghostPanelId = useAtomValue(ghostPanelIdAtom(subSection));
  const maximizedSection = useAtomValue(maximizedSectionAtom);
  const setMaximizedSection = useSetAtom(maximizedSectionAtom);

  const section = toSection(subSection);
  const isMaximized = maximizedSection === section;

  const handleToggleMaximize = (): void => {
    setMaximizedSection(isMaximized ? null : section);
  };

  return (
    <Flex align="center" className={styles.header} data-testid={`${ElementIds.SECTION_HEADER}-${subSection}`}>
      <div className={styles.tabs}>
        {displayedPanelIds.map((panelId) => (
          <PanelTab
            key={panelId}
            panelId={panelId}
            subSection={subSection}
            isActive={panelId === activePanelId}
            isGhost={panelId === ghostPanelId}
          />
        ))}
      </div>
      <Flex align="center" gap="2" className={styles.controls}>
        <AddPanelDropdown
          subSection={subSection}
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
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.headerButton}
          aria-label={isMaximized ? "Restore section" : "Maximize section"}
          title={isMaximized ? "Restore section (Esc)" : "Maximize section"}
          data-testid={`${ElementIds.SECTION_MAXIMIZE_BUTTON}-${subSection}`}
          onClick={handleToggleMaximize}
        >
          {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </IconButton>
      </Flex>
    </Flex>
  );
};

export const SectionHeader = memo(SectionHeaderComponent);
