import { ContextMenu, Flex, IconButton } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Columns2, Maximize2, Minimize2, Plus, Rows2, Trash2, X } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { memo, useCallback, useMemo } from "react";

import { renameWorkspaceAgent } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { formatShortcutForDisplay } from "~/common/ShortcutUtils.ts";
import { updateTasksAtom } from "~/common/state/atoms/tasks.ts";
import { agentDeleteTargetAtom, renamingAgentIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { addPanelTargetZoneAtom } from "~/components/panels/addPanelAtoms.ts";
import {
  activePanelIdInZoneAtom,
  displayedPanelIdsAtom,
  ghostPanelIdAtom,
  isPanelDragActiveAtom,
  panelRegistryAtom,
  panelShortcutsAtom,
  panelsInZoneAtom,
} from "~/components/panels/atoms.ts";
import { useMaximizePanel } from "~/components/panels/hooks.ts";
import type { SectionSide } from "~/components/panels/PanelSection.tsx";
import {
  useActivatePanel,
  useCanSplitSection,
  useRemovePanelFromSection,
  useSplitSection,
} from "~/components/panels/sectionHooks.ts";
import type { SplitAxis } from "~/components/panels/sectionLayoutAtoms.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { TabBar } from "~/components/tabs/TabBar.tsx";
import type { TabDefinition } from "~/components/tabs/types.ts";
import { agentIdFromPanelId, isAgentPanelId } from "~/pages/workspace/panels/dynamicPanels.tsx";
import { isTerminalPanelId, terminalCloseTargetAtom } from "~/pages/workspace/panels/terminals.ts";

import styles from "./PanelSection.module.scss";

type SectionTabBarProps = {
  zone: ZoneId;
  side: SectionSide;
};

/**
 * A section's tab strip: one tab per panel in the zone, the "+" to add panels,
 * and the maximize toggle. Memoized behind primitive props and narrow per-zone
 * atoms so a tab drag only re-renders the strips of the zones it touches.
 *
 * The tab-definition pool is built from the zone's own panels plus (while this
 * zone is a drag target) the incoming ghost tab — NOT from the drag-ordered
 * display list — so insertion-index changes during a drag reorder a plain
 * string array (`openTabIds`) without rebuilding tab objects, and every
 * SortableTab keeps prop identity.
 */
const SectionTabBarInner = ({ zone, side }: SectionTabBarProps): ReactElement => {
  const registry = useAtomValue(panelRegistryAtom);
  const panelIds = useAtomValue(panelsInZoneAtom(zone));
  const ghostPanelId = useAtomValue(ghostPanelIdAtom(zone));
  const displayedPanelIds = useAtomValue(displayedPanelIdsAtom(zone));
  const activePanelId = useAtomValue(activePanelIdInZoneAtom(zone));
  const isDragActive = useAtomValue(isPanelDragActiveAtom);
  const activatePanel = useActivatePanel();
  const removePanel = useRemovePanelFromSection();
  const canSplit = useCanSplitSection(zone);
  const splitSection = useSplitSection(zone);
  const panelShortcuts = useAtomValue(panelShortcutsAtom);
  const { maximizedZone, toggleZone: toggleMaximizeZone } = useMaximizePanel();
  const isMaximized = maximizedZone === zone;
  const setTerminalCloseTarget = useSetAtom(terminalCloseTargetAtom);
  const updateTasks = useSetAtom(updateTasksAtom);
  const setRenamingAgentId = useSetAtom(renamingAgentIdAtom);
  const renamingAgentId = useAtomValue(renamingAgentIdAtom);
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);

  const { workspaceID } = useWorkspacePageParams();
  const openPalette = useSetAtom(addPanelTargetZoneAtom);

  // The tab-definition pool: this zone's panels, plus the dragged tab while it
  // previews here. Membership only changes when the ghost enters/leaves the
  // zone — not on every insertion-index change.
  const poolPanelIds = useMemo<ReadonlyArray<PanelId>>(
    () => (ghostPanelId !== null && !panelIds.includes(ghostPanelId) ? [...panelIds, ghostPanelId] : panelIds),
    [panelIds, ghostPanelId],
  );

  const handleRenameCommit = useCallback(
    (agentId: string, newName: string): void => {
      setRenamingAgentId(null);
      void renameWorkspaceAgent({ path: { workspace_id: workspaceID, agent_id: agentId }, body: { title: newName } })
        .then((response) => {
          if (response.data) updateTasks({ [agentId]: response.data });
        })
        .catch((error) => console.error("Failed to rename agent:", error));
    },
    [workspaceID, setRenamingAgentId, updateTasks],
  );

  const tabs = useMemo<Array<TabDefinition>>(
    () =>
      poolPanelIds.flatMap((panelId) => {
        const def = registry.find((p) => p.id === panelId);
        if (!def) return [];
        const isRenaming = isAgentPanelId(panelId) && renamingAgentId === agentIdFromPanelId(panelId);
        const binding = panelShortcuts[panelId];
        return [
          {
            id: panelId,
            label: def.displayName,
            // Only agents keep a leading icon (their live status dot, `tabIcon`);
            // static panels and terminals render label-only (REQ-ICONS-1).
            icon: def.tabIcon,
            dataTestId: `panel-tab-${panelId}`,
            // Scopes the label truncation in SortableTab.module.scss to panel-section
            // tabs so the diff tab bar (the other compact strip) is unaffected.
            dataAttributes: { "section-tab": "true" },
            shortcut: binding ? formatShortcutForDisplay(binding) : undefined,
            // Every tab is closeable now, including the only agent: closing it
            // deletes the agent (with confirmation), and the delete flow keeps a
            // workspace at ≥1 agent by spawning a fresh one — so there's always
            // something to fall back to (see handleClose).
            labelContent: isRenaming ? (
              <InlineRenameInput
                value={def.displayName}
                onCommit={(newName) => handleRenameCommit(agentIdFromPanelId(panelId), newName)}
                onCancel={() => setRenamingAgentId(null)}
                isEditing
              />
            ) : undefined,
          },
        ];
      }),
    [poolPanelIds, registry, renamingAgentId, handleRenameCommit, setRenamingAgentId, panelShortcuts],
  );

  const handleActivate = useCallback((panelId: string): void => activatePanel(panelId, zone), [activatePanel, zone]);

  // Closing an agent or terminal tab ends it (after confirmation), rather than
  // parking it for re-add: the X opens the same confirm dialog as the context
  // menu. Agent → delete (`agentDeleteTargetAtom`; the delete flow in
  // AgentWorkspaceCommands handles post-delete navigation and keeps the
  // workspace at ≥1 agent). Terminal → close its session
  // (`terminalCloseTargetAtom`, handled by TerminalCloseConfirmation). Static
  // panels are simply unplaced from the section.
  const handleClose = useCallback(
    (panelId: PanelId): void => {
      const def = registry.find((p) => p.id === panelId);
      if (isAgentPanelId(panelId)) {
        setAgentDeleteTarget({ id: agentIdFromPanelId(panelId), name: def?.displayName ?? "" });
        return;
      }

      if (isTerminalPanelId(panelId)) {
        setTerminalCloseTarget({ id: panelId, name: def?.displayName ?? "" });
        return;
      }
      removePanel(panelId);
    },
    [registry, setAgentDeleteTarget, setTerminalCloseTarget, removePanel],
  );

  const handleDoubleClick = useCallback(
    (panelId: PanelId): void => {
      if (isAgentPanelId(panelId)) setRenamingAgentId(agentIdFromPanelId(panelId));
    },
    [setRenamingAgentId],
  );

  const contextMenuContent = useCallback(
    (panelId: PanelId): ReactNode => {
      // Which split axes a section offers depends on its side: the tall Left /
      // Right columns split only top/bottom ("horizontal"); the wide Bottom bar
      // splits only side-by-side ("vertical"); the Center allows both.
      // ("Split horizontally" = stacked top/bottom; "Split vertically" =
      // side-by-side.)
      const allowedSplitAxes: ReadonlyArray<SplitAxis> =
        side === "bottom" ? ["vertical"] : side === "center" ? ["horizontal", "vertical"] : ["horizontal"];

      // Offered on every tab while the section can still be split (a primary
      // section that isn't already split — see useCanSplitSection).
      const splitItems = canSplit ? (
        <>
          {allowedSplitAxes.includes("horizontal") && (
            <ContextMenu.Item onSelect={() => splitSection(panelId, "horizontal")}>
              <Rows2 size={14} /> Split horizontally
            </ContextMenu.Item>
          )}
          {allowedSplitAxes.includes("vertical") && (
            <ContextMenu.Item onSelect={() => splitSection(panelId, "vertical")}>
              <Columns2 size={14} /> Split vertically
            </ContextMenu.Item>
          )}
        </>
      ) : null;

      if (isAgentPanelId(panelId)) {
        const agentId = agentIdFromPanelId(panelId);
        const def = registry.find((p) => p.id === panelId);
        return (
          <ContextMenu.Content size="1">
            {splitItems}
            {splitItems && <ContextMenu.Separator />}
            <ContextMenu.Item onSelect={() => setRenamingAgentId(agentId)}>Rename</ContextMenu.Item>
            <ContextMenu.Separator />
            <ContextMenu.Item
              color="red"
              onSelect={() => setAgentDeleteTarget({ id: agentId, name: def?.displayName ?? "" })}
            >
              <Trash2 size={14} /> Delete agent
            </ContextMenu.Item>
          </ContextMenu.Content>
        );
      }

      if (isTerminalPanelId(panelId)) {
        return (
          <ContextMenu.Content size="1">
            {splitItems}
            {splitItems && <ContextMenu.Separator />}
            <ContextMenu.Item
              color="red"
              onSelect={() =>
                setTerminalCloseTarget({ id: panelId, name: registry.find((p) => p.id === panelId)?.displayName ?? "" })
              }
            >
              <X size={14} /> Close terminal
            </ContextMenu.Item>
          </ContextMenu.Content>
        );
      }

      // Static panels: only the split actions, and only when available.
      if (!splitItems) return undefined;
      return <ContextMenu.Content size="1">{splitItems}</ContextMenu.Content>;
    },
    [side, canSplit, splitSection, registry, setRenamingAgentId, setAgentDeleteTarget, setTerminalCloseTarget],
  );

  // Rendered as a TabBar child that fills the rest of the strip: the "+" sits
  // inline right after the last tab while the maximize button is pushed to the
  // far right (justify between). The "+" opens the Add Panel palette scoped to
  // this section; the maximize button blows this section up to fill the
  // workspace (and becomes a restore button while maximized).
  const sectionControls = (
    <Flex align="center" justify="between" className={styles.addButton}>
      <IconButton
        variant="ghost"
        size="1"
        color="gray"
        className={styles.headerButton}
        aria-label="Add panel"
        data-testid={`panel-section-add-${side}`}
        onClick={() => openPalette(zone)}
      >
        <Plus size={14} />
      </IconButton>
      <IconButton
        variant="ghost"
        size="1"
        color="gray"
        className={styles.headerButton}
        aria-label={isMaximized ? "Restore panel" : "Maximize panel"}
        title={isMaximized ? "Restore panel (Esc)" : "Maximize panel"}
        data-testid={`panel-section-maximize-${side}`}
        onClick={() => toggleMaximizeZone(zone)}
      >
        {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </IconButton>
    </Flex>
  );

  return (
    <TabBar
      tabs={tabs}
      openTabIds={displayedPanelIds as Array<string>}
      activeTabId={activePanelId ?? ""}
      onActivate={handleActivate}
      onClose={handleClose}
      onDoubleClick={handleDoubleClick}
      contextMenuContent={contextMenuContent}
      variant="compact"
      dndMode="shared"
      externalDragActive={isDragActive}
      alwaysCloseable
      tabBarClassName={styles.tabBar}
    >
      {sectionControls}
    </TabBar>
  );
};

export const SectionTabBar = memo(SectionTabBarInner);
