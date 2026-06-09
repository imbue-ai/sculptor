import { useDroppable } from "@dnd-kit/core";
import { ContextMenu, DropdownMenu, IconButton } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Columns2, MessageSquarePlus, Plus, Rows2, SquareTerminal, Trash2, X } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useMemo } from "react";

import { renameWorkspaceAgent } from "~/api";
import { useImbueLocation, useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { updateTasksAtom } from "~/common/state/atoms/tasks.ts";
import { agentDeleteTargetAtom, renamingAgentIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import {
  activePanelPerZoneAtom,
  computeDisplayedPanelIds,
  panelDragStateAtom,
  panelRegistryAtom,
  panelsInZoneAtom,
  zoneAssignmentsAtom,
} from "~/components/panels/atoms.ts";
import {
  useActivatePanel,
  useCanSplitSection,
  useRemovePanelFromSection,
  useSplitSection,
} from "~/components/panels/sectionHooks.ts";
import { tabStripPositionAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { TabBar } from "~/components/tabs/TabBar.tsx";
import type { TabDefinition } from "~/components/tabs/types.ts";
import { agentIdFromPanelId, isAgentPanelId } from "~/pages/workspace/panels/dynamicPanels.tsx";
import { isTerminalPanelId, removeTerminalAtom } from "~/pages/workspace/panels/terminals.ts";
import { useAddPanelMenu } from "~/pages/workspace/panels/useAddPanelMenu.ts";

import styles from "./PanelSection.module.scss";

export type SectionSide = "left" | "center" | "right" | "bottom";

type PanelSectionProps = {
  zone: ZoneId;
  side: SectionSide;
};

/**
 * One uniform panel section (Left / Center / Right / Bottom). Renders a single
 * tab strip — at the top or bottom per the global setting (REQ-SET-1) — a "+"
 * to add panels/agents/terminals not currently here, and the active panel's
 * content. A section never auto-collapses; it can sit open and empty showing
 * just "+" (REQ-SECTION-1..3).
 */
export const PanelSection = ({ zone, side }: PanelSectionProps): ReactElement => {
  const registry = useAtomValue(panelRegistryAtom);
  const panelIds = useAtomValue(panelsInZoneAtom(zone));
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const activePanelPerZone = useAtomValue(activePanelPerZoneAtom);
  const dragState = useAtomValue(panelDragStateAtom);
  const tabStripPosition = useAtomValue(tabStripPositionAtom);
  const activatePanel = useActivatePanel();
  const removePanel = useRemovePanelFromSection();
  const canSplit = useCanSplitSection(zone);
  const splitSection = useSplitSection(zone);
  const removeTerminal = useSetAtom(removeTerminalAtom);
  const updateTasks = useSetAtom(updateTasksAtom);
  const setRenamingAgentId = useSetAtom(renamingAgentIdAtom);
  const renamingAgentId = useAtomValue(renamingAgentIdAtom);
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);

  const { workspaceID } = useWorkspacePageParams();
  const { agentId: urlAgentId } = useImbueLocation();
  const { navigateToAgent } = useImbueNavigate();
  const menu = useAddPanelMenu(zone);

  // The whole section is a drop target for tab drags (its zone is the droppable
  // id). The PanelDndProvider's shared DndContext drives the move on drop.
  const { setNodeRef: setDroppableRef } = useDroppable({ id: zone });

  // While a tab is being dragged, render the dragged panel relocated into the
  // target section at the insertion index — so a ghost copy previews where it
  // will land — without mutating the persisted zone state until drop.
  const displayedPanelIds = useMemo(
    () => computeDisplayedPanelIds({ zone, panelIds, drag: dragState }),
    [zone, panelIds, dragState],
  );
  const isDropTarget = dragState !== null && dragState.targetZone === zone && dragState.sourceZone !== zone;

  const activePanelId: PanelId | undefined =
    activePanelPerZone[zone] && panelIds.includes(activePanelPerZone[zone]!) ? activePanelPerZone[zone] : panelIds[0];

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
      displayedPanelIds.flatMap((panelId) => {
        const def = registry.find((p) => p.id === panelId);
        if (!def) return [];
        const Icon = def.icon;
        const isRenaming = isAgentPanelId(panelId) && renamingAgentId === agentIdFromPanelId(panelId);
        return [
          {
            id: panelId,
            label: def.displayName,
            icon: def.tabIcon ?? <Icon size={13} />,
            dataTestId: `panel-tab-${panelId}`,
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
    [displayedPanelIds, registry, renamingAgentId, handleRenameCommit, setRenamingAgentId],
  );

  // Closing a tab removes the panel from this section (returns it to the "+"
  // pool) — it does not delete agents or kill terminals (REQ-INST-1). The active
  // agent is kept on screen by the bootstrap invariant, so closing it focuses
  // another open agent first when one exists. The sibling search spans all
  // sections (zoneAssignments), not just this one, so closing the active agent
  // still works when the other agent lives in this section's other split half.
  const handleClose = useCallback(
    (panelId: PanelId): void => {
      if (isAgentPanelId(panelId) && agentIdFromPanelId(panelId) === urlAgentId) {
        const otherAgent = Object.keys(zoneAssignments).find((id) => isAgentPanelId(id) && id !== panelId);
        if (!otherAgent) return; // can't close the only/active agent
        navigateToAgent(workspaceID, agentIdFromPanelId(otherAgent));
      }
      removePanel(panelId);
    },
    [zoneAssignments, urlAgentId, navigateToAgent, workspaceID, removePanel],
  );

  const handleDoubleClick = useCallback(
    (panelId: PanelId): void => {
      if (isAgentPanelId(panelId)) setRenamingAgentId(agentIdFromPanelId(panelId));
    },
    [setRenamingAgentId],
  );

  const contextMenuContent = useCallback(
    (panelId: PanelId): ReactNode => {
      // "Split horizontally" = stacked top/bottom; "Split vertically" =
      // side-by-side. Offered on every tab while the section can still be split
      // (a primary section that isn't already split — see useCanSplitSection).
      const splitItems = canSplit ? (
        <>
          <ContextMenu.Item onSelect={() => splitSection(panelId, "horizontal")}>
            <Rows2 size={14} /> Split horizontally
          </ContextMenu.Item>
          <ContextMenu.Item onSelect={() => splitSection(panelId, "vertical")}>
            <Columns2 size={14} /> Split vertically
          </ContextMenu.Item>
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
              onSelect={() => {
                removeTerminal(panelId);
                removePanel(panelId);
              }}
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
    [canSplit, splitSection, registry, setRenamingAgentId, setAgentDeleteTarget, removeTerminal, removePanel],
  );

  const ActivePanelComponent = activePanelId ? registry.find((p) => p.id === activePanelId)?.component : undefined;

  // Rendered as a TabBar child so the "+" sits inline right after the last tab
  // rather than pinned to the far right of the strip.
  const addButton = (
    <div className={styles.addButton}>
      <AddPanelDropdown side={side} menu={menu}>
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.headerButton}
          aria-label="Add panel"
          data-testid={`panel-section-add-${side}`}
        >
          <Plus size={14} />
        </IconButton>
      </AddPanelDropdown>
    </div>
  );

  const tabBar = (
    <TabBar
      tabs={tabs}
      openTabIds={displayedPanelIds as Array<string>}
      activeTabId={activePanelId ?? ""}
      onActivate={(id) => activatePanel(id, zone)}
      onClose={handleClose}
      onDoubleClick={handleDoubleClick}
      contextMenuContent={contextMenuContent}
      variant="compact"
      dndMode="shared"
      externalDragActive={dragState !== null}
      alwaysCloseable
      closeReplacesIcon
      tabBarClassName={styles.tabBar}
    >
      {addButton}
    </TabBar>
  );

  return (
    <div
      ref={setDroppableRef}
      className={`${styles.section} ${isDropTarget ? styles.dropTarget : ""}`}
      data-testid={`panel-section-${side}`}
    >
      {tabStripPosition === "top" && tabBar}
      <div className={styles.content} data-zone-id={zone} tabIndex={-1}>
        {ActivePanelComponent ? (
          <ActivePanelComponent />
        ) : (
          <div className={styles.emptyState}>
            <AddPanelDropdown side="center" menu={menu}>
              <IconButton variant="soft" size="2" color="gray" aria-label="Add a panel">
                <Plus size={18} />
              </IconButton>
            </AddPanelDropdown>
            <span className={styles.emptyHint}>Add a panel</span>
          </div>
        )}
      </div>
      {tabStripPosition === "bottom" && tabBar}
    </div>
  );
};

type AddPanelDropdownProps = {
  side: SectionSide;
  menu: ReturnType<typeof useAddPanelMenu>;
  children: ReactNode;
};

const AddPanelDropdown = ({ side, menu, children }: AddPanelDropdownProps): ReactElement => {
  const { staticPanels, existingAgents, existingTerminals, openPanel, createAgent, createTerminal } = menu;
  const align = side === "right" ? "end" : "start";
  const isEmpty = staticPanels.length === 0 && existingAgents.length === 0 && existingTerminals.length === 0;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>{children}</DropdownMenu.Trigger>
      <DropdownMenu.Content size="1" align={align}>
        <DropdownMenu.Item onSelect={createAgent}>
          <MessageSquarePlus size={14} /> New Agent
        </DropdownMenu.Item>
        <DropdownMenu.Item onSelect={createTerminal}>
          <SquareTerminal size={14} /> New Terminal
        </DropdownMenu.Item>

        {!isEmpty && <DropdownMenu.Separator />}

        {existingAgents.map((panel) => (
          <DropdownMenu.Item key={panel.id} onSelect={() => openPanel(panel.id)}>
            {panel.tabIcon} {panel.displayName}
          </DropdownMenu.Item>
        ))}
        {existingTerminals.map((panel) => {
          const Icon = panel.icon;
          return (
            <DropdownMenu.Item key={panel.id} onSelect={() => openPanel(panel.id)}>
              <Icon size={14} /> {panel.displayName}
            </DropdownMenu.Item>
          );
        })}
        {staticPanels.map((panel) => {
          const Icon = panel.icon;
          return (
            <DropdownMenu.Item key={panel.id} onSelect={() => openPanel(panel.id)}>
              <Icon size={14} /> {panel.displayName}
            </DropdownMenu.Item>
          );
        })}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};
