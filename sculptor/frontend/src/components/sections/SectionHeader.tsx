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
import { useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import { Maximize2, Minimize2, Plus, X } from "lucide-react";
import type { ReactElement } from "react";
import { memo, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { agentRenameTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { sidebarCollapsedAtom } from "~/components/layout/sidebarAtoms.ts";
import { AgentStatusDot } from "~/components/statusDot";
import { getCollapsedSidebarToggleClearance } from "~/electron/utils.ts";
import { getTabStatusIcon } from "~/pages/workspace/panels/TerminalConnectionIndicator.tsx";

import { AddPanelDropdown } from "./AddPanelDropdown.tsx";
import type { PanelContextMenuItem, PanelDefinition } from "./registry/panelRegistry.ts";
import {
  panelDefinitionByIdAtom,
  panelRegistryAtom,
  resolvedActivePanelIdInSubSectionAtom,
} from "./registry/panelRegistry.ts";
import { isMultiInstanceKind } from "./registry/panelRegistry.ts";
import { closePanelAtom, setActivePanelAtom, splitSectionAtom } from "./sectionActions.ts";
import { sectionSplitForSectionAtom } from "./sectionAtoms.ts";
import styles from "./SectionHeader.module.scss";
import type { PanelId, SubSectionId } from "./sectionTypes.ts";
import { splitDirectionOptionsForSection, toSection } from "./sectionTypes.ts";
import { TabPill } from "./TabPill.tsx";
import {
  displayedPanelIdsAtom,
  ghostPanelIdAtom,
  isMaximizedSectionAtom,
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
  const store = useStore();
  const [isRenaming, setIsRenaming] = useState<boolean>(false);
  // The command palette's agent rename sets this to the panel id it wants
  // renamed; the matching tab reacts by entering inline rename below.
  const [agentRenameTarget, setAgentRenameTarget] = useAtom(agentRenameTargetAtom);
  const labelRef = useRef<HTMLSpanElement>(null);
  const [isLabelTruncated, setIsLabelTruncated] = useState<boolean>(false);
  // The context-menu items shown while the menu is open, resolved fresh on each open
  // (see resolveLiveDefinition below).
  const [openMenuActions, setOpenMenuActions] = useState<ReadonlyArray<PanelContextMenuItem>>([]);
  const section = toSection(subSection);
  const existingSplit = useAtomValue(sectionSplitForSectionAtom(section));
  const splitPanel = useSetAtom(splitSectionAtom);
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } = useDraggable({
    id: panelId,
    data: { kind: "panel", panelId, from: subSection, index },
  });

  // When the command palette targets THIS tab for rename, flip into inline edit
  // and clear the atom so a later re-render doesn't re-open the editor. Only
  // multi-instance panels (agent/terminal) can rename; a target that names a
  // single-instance panel is dropped so it can't get stuck pending.
  useEffect(() => {
    if (agentRenameTarget !== panelId) return;
    if (definition !== undefined && isMultiInstanceKind(definition.kind)) {
      setIsRenaming(true);
    }
    setAgentRenameTarget(null);
  }, [agentRenameTarget, panelId, definition, setAgentRenameTarget]);

  if (definition === undefined) {
    return null;
  }

  const canRename = isMultiInstanceKind(definition.kind);

  // `definition` comes through the equality-guarded per-id slice, which deliberately
  // suppresses callback-only changes (see panelDefinitionEqual) — so its callbacks and
  // context-menu actions can be stale (e.g. copy actions built before the agent's
  // diagnostics arrived). Anything the user invokes therefore re-reads the CURRENT
  // definition from the registry at interaction time; the slice is only trusted for
  // the render-relevant fields the comparator covers.
  const resolveLiveDefinition = (): PanelDefinition =>
    store.get(panelRegistryAtom).find((candidate) => candidate.id === panelId) ?? definition;

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

  // Enter activates the panel from the keyboard, like a click. Space is
  // deliberately NOT handled here: every other key falls through to the dnd-kit
  // keyboard sensor's activator (listeners.onKeyDown), so the documented drag
  // pipeline (focus tab → Space → arrows → Space) keeps working while Enter can
  // never start a drag. Guards: only keys targeted at the tab itself count (an
  // Enter on the close button or inside the rename input is theirs), and while
  // THIS tab is mid-drag Enter is the sensor's drop-commit key, so it is left
  // alone rather than activating the panel out from under the drag.
  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter" && event.target === event.currentTarget && !isDragging) {
      event.preventDefault();
      handleActivate();
      return;
    }
    listeners?.onKeyDown?.(event);
  };

  // Double-clicking a multi-instance tab starts an inline rename; the context-menu
  // Rename item is the other entry.
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
    const liveDefinition = resolveLiveDefinition();
    if (liveDefinition.onRequestClose !== undefined) {
      liveDefinition.onRequestClose();
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
    resolveLiveDefinition().onRename?.(newName);
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

  // The label ellipsis-clips at a fixed max-width, so a tooltip is only useful when the
  // text is actually cut off. Truncation is measured on hover (scrollWidth vs
  // clientWidth) rather than via a ResizeObserver: the tab strip re-renders heavily
  // during drags, and measuring at hover time reads layout exactly when the tooltip
  // could appear — no observer to keep alive across those churny re-renders.
  const labelSpan = (
    <span
      ref={labelRef}
      className={styles.label}
      onMouseEnter={() => {
        const el = labelRef.current;
        if (el !== null) {
          setIsLabelTruncated(el.scrollWidth > el.clientWidth);
        }
      }}
    >
      {definition.displayName}
    </span>
  );

  const tabBody = (
    <div
      ref={setTabRef}
      className={tabClassName}
      {...attributes}
      {...(isRenaming ? {} : listeners)}
      // After the listeners spread so this composed handler REPLACES the sensor's
      // raw onKeyDown (it delegates every non-Enter key back to it).
      onKeyDown={isRenaming ? undefined : handleKeyDown}
      role="tab"
      aria-selected={isActive}
      data-testid={`${ElementIds.PANEL_TAB}-${panelId}`}
      data-section-tab="true"
      data-panel-id={panelId}
      data-dot-status={definition.dotStatus}
      onClick={handleActivate}
      onDoubleClick={handleDoubleClick}
    >
      {definition.dotStatus !== undefined && (
        <div
          className={styles.dot}
          data-testid={ElementIds.PANEL_TAB_STATUS_DOT}
          data-panel-tab-dot={definition.dotStatus}
          aria-hidden="true"
        >
          <AgentStatusDot status={definition.dotStatus} size={8} />
        </div>
      )}
      {/* A terminal's connection-issue dot (amber pulsing = reconnecting, red static =
          disconnected). Only terminal panels carry connectionStatus and they never carry
          dotStatus, so the two dot slots are mutually exclusive. getTabStatusIcon emits
          the TERMINAL_TAB_STATUS_INDICATOR testid + data-status the harness reads. */}
      {definition.connectionStatus !== undefined && (
        <div className={styles.dot} aria-hidden="true">
          {getTabStatusIcon(definition.connectionStatus)}
        </div>
      )}
      {isRenaming && canRename ? (
        <InlineRenameInput
          value={definition.displayName}
          onCommit={handleRenameCommit}
          onCancel={() => setIsRenaming(false)}
          isEditing
        />
      ) : isLabelTruncated ? (
        <Tooltip content={definition.displayName}>{labelSpan}</Tooltip>
      ) : (
        labelSpan
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

  // The (possibly stale) slice is only used for the has-a-menu decision — whether a
  // panel carries context actions at all never changes over its lifetime. The items
  // themselves render from openMenuActions, resolved fresh on each open.
  const hasContextMenu = canRename || (definition.contextMenuActions ?? []).length > 0 || splitOptions.length > 0;

  if (!hasContextMenu) {
    return tabBody;
  }

  const hasMenuAboveSplits = canRename || openMenuActions.length > 0;

  const handleMenuOpenChange = (open: boolean): void => {
    if (open) {
      // Resolve the actions at open time so async updates since the slice last
      // re-emitted (e.g. diagnostics arriving after a status change) are reflected in
      // the items' disabled state and captured values.
      setOpenMenuActions(resolveLiveDefinition().contextMenuActions ?? []);
    }
  };

  return (
    <ContextMenu.Root onOpenChange={handleMenuOpenChange}>
      <ContextMenu.Trigger>{tabBody}</ContextMenu.Trigger>
      <ContextMenu.Content size="1">
        {canRename && (
          <ContextMenu.Item data-testid={ElementIds.TAB_CONTEXT_MENU_RENAME} onSelect={() => setIsRenaming(true)}>
            Rename
          </ContextMenu.Item>
        )}
        {canRename && openMenuActions.length > 0 && <ContextMenu.Separator />}
        {openMenuActions.map((action) => (
          <ContextMenu.Item
            key={action.label}
            disabled={action.disabled}
            data-testid={action.testId}
            onSelect={() => action.action()}
          >
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

type SectionHeaderProps = { subSection: SubSectionId };

const SectionHeaderComponent = ({ subSection }: SectionHeaderProps): ReactElement => {
  const displayedPanelIds = useAtomValue(displayedPanelIdsAtom(subSection));
  // The registry-aware resolved id — the same atom SectionBody renders from — so the
  // highlighted tab always matches the rendered body, including when the persisted
  // active id is an unregistered (unloaded/still-loading) plugin panel and the body
  // falls back to another open panel.
  const activePanelId = useAtomValue(resolvedActivePanelIdInSubSectionAtom(subSection));
  const ghostPanelId = useAtomValue(ghostPanelIdAtom(subSection));
  const isReorderWithin = useAtomValue(isReorderWithinSubSectionAtom(subSection));
  const setMaximizedSection = useSetAtom(maximizedSectionAtom);
  const isSidebarCollapsed = useAtomValue(sidebarCollapsedAtom);

  const section = toSection(subSection);
  // Per-section slice: a maximize flip re-renders only the affected headers.
  const isMaximized = useAtomValue(isMaximizedSectionAtom(section));

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
        ...(isSidebarCollapsed ? { paddingLeft: getCollapsedSidebarToggleClearance() } : {}),
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
      {/* The strip is a tablist for assistive tech; the drag ghost pill inside it is
          aria-hidden, so tabs are its only exposed children. */}
      <div className={styles.tabs} role="tablist" aria-orientation="horizontal" data-section-tabs={subSection}>
        {displayedPanelIds.map((panelId, index) => {
          // A cross-section drag shows a non-draggable ghost here while the real
          // draggable stays in the source section; a within-section reorder keeps the
          // single instance fully draggable at its preview slot.
          if (panelId === ghostPanelId && !isReorderWithin) {
            return <TabPill key={panelId} panelId={panelId} variant="ghost" />;
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
