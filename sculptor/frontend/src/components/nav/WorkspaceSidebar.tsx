import type { DragEndEvent } from "@dnd-kit/core";
import { closestCenter, DndContext } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom, useStore } from "jotai";
import { Bug, Command, Home, PanelLeftClose, PanelsTopLeft, Plus, Settings } from "lucide-react";
import { Tooltip as TooltipPrimitive } from "radix-ui";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Workspace } from "~/api";
import { ElementIds } from "~/api";
import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import { agentIdsByWorkspaceAtom, ensurePseudoTabAtom } from "~/common/state/atoms/workspaces.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { AddRepoDialog } from "~/components/add-repo/AddRepoDialog.tsx";
import { useCommandPalette } from "~/components/CommandPalette";
import { renamingWorkspaceIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import type { OpenInRuntime } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceActionRuntime } from "~/components/CommandPalette/contextActions/types.ts";
import { useGitAndOpenInRuntime } from "~/components/CommandPalette/contextActions/useGitAndOpenInRuntime.ts";
import { buildWorkspaceActions } from "~/components/CommandPalette/contextActions/workspaceActions.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { DevModeIndicator } from "~/components/DevModeIndicator.tsx";
import { sidebarCollapsedAtom, sidebarWidthAtom } from "~/components/layout/sidebarAtoms.ts";
import { layoutsSwitcherOpenAtom } from "~/components/layouts/layoutUiAtoms.ts";
import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { ReportProblemPopover } from "~/components/ReportProblemPopover.tsx";
import { layoutPersistenceAdapter } from "~/components/sections/persistence/LocalStorageLayoutAdapter.ts";
import { ResizeHandle } from "~/components/sections/ResizeHandle.tsx";
import { Toast, type ToastContent } from "~/components/Toast.tsx";
import { useWorkspaceTabActions } from "~/components/useWorkspaceTabActions.ts";
import { VersionPopover } from "~/components/VersionPopover.tsx";
import { HOME_TAB_ID, SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";
import { WorkspacePeekOverlay } from "~/pages/workspace/components/WorkspacePeekOverlay.tsx";

import { adjustSidebarDragCountAtom, isSidebarDragActiveAtom } from "./navAtoms.ts";
import navItemStyles from "./NavItem.module.scss";
import { NavItem } from "./NavItem.tsx";
import { sidebarDndModifiers, useSidebarDndSensors } from "./sidebarDnd.ts";
import { SidebarRepoGroup } from "./SidebarRepoGroup.tsx";
import { reorderSidebarRepoGroupAtom, sidebarWorkspaceGroupsAtom } from "./sidebarWorkspaceOrder.ts";
import styles from "./WorkspaceSidebar.module.scss";

/** Smallest sidebar width the resize handle allows, in pixels. */
const MIN_SIDEBAR_WIDTH_PX = 180;

/**
 * Vertical navigation sidebar — the global chrome rail that replaces the old
 * top bar. Top links (Home / Cmd+K / New workspace), then repos
 * as collapsible groups with their workspaces, then Settings / report-a-bug /
 * version anchored to the bottom. A drag handle on the right border resizes it
 * and the collapse toggle hides it down to `CollapsedSidebarToggle`. Width and
 * collapsed state persist globally via the layout snapshot.
 */
export const WorkspaceSidebar = (): ReactElement | null => {
  // External atoms
  const isCollapsed = useAtomValue(sidebarCollapsedAtom);
  const setCollapsed = useSetAtom(sidebarCollapsedAtom);
  const width = useAtomValue(sidebarWidthAtom);
  const setWidth = useSetAtom(sidebarWidthAtom);
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);
  // Grouped + sorted repo groups (one per repo, including repos with no
  // workspaces yet), shared with keyboard workspace cycling so the two can't
  // drift (see sidebarWorkspaceOrder).
  const repoGroups = useAtomValue(sidebarWorkspaceGroupsAtom);
  const setRenamingWorkspaceId = useSetAtom(renamingWorkspaceIdAtom);
  // The workspace→last-agent map is only consulted inside the click handler, so
  // read it lazily from the store rather than subscribing: the whole sidebar
  // would otherwise re-render (and churn the click callbacks) on every agent-id
  // change, with no visual effect.
  const store = useStore();

  // Internal state — the add-repo dialog opened from the "Add repo" nav button
  // (and its toast).
  const [isAddRepoDialogOpen, setIsAddRepoDialogOpen] = useState<boolean>(false);
  const [addRepoToast, setAddRepoToast] = useState<ToastContent | null>(null);
  // Deleting a workspace is destructive, so it is confirmed first. The trash
  // icon and both Delete menu entries set this target to open the shared
  // confirmation dialog; confirming runs the optimistic delete below.
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);

  // External hooks
  const { navigateToWorkspace, navigateToAgent, navigateToHome, navigateToGlobalSettings } = useImbueNavigate();
  const setNewWorkspaceModal = useSetAtom(newWorkspaceModalAtom);
  const { toggle: toggleCommandPalette } = useCommandPalette();
  const { workspaceId: activeWorkspaceId, isHomeRoute, isSettingsRoute, isWorkspaceRoute } = useImbueLocation();
  const setLayoutsSwitcherOpen = useSetAtom(layoutsSwitcherOpenAtom);
  const { navigateToNextTab } = useWorkspaceTabActions();
  const gitAndOpenIn = useGitAndOpenInRuntime();
  // Deleting a workspace updates the sidebar optimistically and rolls back with
  // an error toast on failure. Navigate away only when the deleted
  // workspace is the active one.
  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    onNavigateAfterDelete: (workspaceId): void => {
      if (workspaceId === activeWorkspaceId) {
        navigateToNextTab(workspaceId);
      }
    },
  });

  // Functions and callbacks
  const workspaceActionRuntime = useMemo<WorkspaceActionRuntime>(
    () => ({
      beginRename: (ws): void => setRenamingWorkspaceId(ws.objectId),
      beginDelete: (ws): void => setDeleteTarget(ws),
      ...gitAndOpenIn,
    }),
    [setRenamingWorkspaceId, gitAndOpenIn],
  );

  // Run the optimistic delete once the user confirms in the dialog.
  const handleDeleteConfirm = useCallback((): void => {
    if (deleteTarget === null) {
      return;
    }
    executeDelete(deleteTarget.objectId, deleteTarget.description ?? "");
    setDeleteTarget(null);
  }, [deleteTarget, executeDelete]);
  const workspaceActions = useMemo(() => buildWorkspaceActions(workspaceActionRuntime), [workspaceActionRuntime]);
  const openInRuntime = useMemo<OpenInRuntime>(
    () => ({
      openInApp: gitAndOpenIn.openInApp,
      canOpenInOS: gitAndOpenIn.canOpenInOS,
      isMacUi: gitAndOpenIn.isMacUi,
    }),
    [gitAndOpenIn],
  );

  const handleWorkspaceClick = useCallback(
    (workspaceId: string): void => {
      const savedAgentId = store.get(agentIdsByWorkspaceAtom).get(workspaceId);
      if (savedAgentId) {
        navigateToAgent(workspaceId, savedAgentId);
        return;
      }
      navigateToWorkspace(workspaceId);
    },
    [store, navigateToAgent, navigateToWorkspace],
  );

  // Navigation-intent prefetch seam: warm the workspace's persisted layout
  // on hover. A no-op for the localStorage adapter (reads are synchronous); the seam is
  // here so the future backend adapter can fetch the snapshot before the user clicks.
  const handleWorkspaceHover = useCallback((workspaceId: string): void => {
    layoutPersistenceAdapter.prefetch?.({ kind: "workspace", workspaceId });
  }, []);

  // The hover peek popover (anchored beside the row) navigates to the workspace,
  // or to a specific agent when one of its agent rows is clicked.
  const handlePeekNavigate = useCallback(
    (workspaceId: string, agentId?: string): void => {
      if (agentId) {
        navigateToAgent(workspaceId, agentId);
        return;
      }
      handleWorkspaceClick(workspaceId);
    },
    [navigateToAgent, handleWorkspaceClick],
  );

  const handleOpenHome = useCallback((): void => {
    ensurePseudoTab(HOME_TAB_ID);
    navigateToHome();
  }, [ensurePseudoTab, navigateToHome]);

  const handleOpenSettings = useCallback((): void => {
    ensurePseudoTab(SETTINGS_TAB_ID);
    navigateToGlobalSettings();
  }, [ensurePseudoTab, navigateToGlobalSettings]);

  const handleResize = useCallback(
    (nextSizePx: number): void => {
      setWidth(Math.max(MIN_SIDEBAR_WIDTH_PX, nextSizePx));
    },
    [setWidth],
  );

  // Repo groups are drag-sortable (each group's rows have their own context inside
  // SidebarRepoGroup); a drop commits the new group order to the layout snapshot.
  const groupDndSensors = useSidebarDndSensors();
  // Stamped on the sidebar root as a data flag so the stylesheet can suppress
  // hover chrome for the whole rail while any sidebar drag is active.
  const isSidebarDragActive = useAtomValue(isSidebarDragActiveAtom);
  const adjustDragCount = useSetAtom(adjustSidebarDragCountAtom);
  const reorderRepoGroup = useSetAtom(reorderSidebarRepoGroupAtom);

  // Whether the in-flight sidebar drag was started by the group context. Every
  // drag context adjusts the shared drag count, so end/cancel/cleanup must only
  // decrement for a drag they own — an unowning cleanup would otherwise release
  // a row drag still parked in some group.
  const ownsActiveDragRef = useRef(false);
  const beginOwnedDrag = useCallback((): void => {
    if (!ownsActiveDragRef.current) {
      ownsActiveDragRef.current = true;
      adjustDragCount(1);
    }
  }, [adjustDragCount]);
  const endOwnedDrag = useCallback((): void => {
    if (ownsActiveDragRef.current) {
      ownsActiveDragRef.current = false;
      adjustDragCount(-1);
    }
  }, [adjustDragCount]);
  const handleGroupDragEnd = useCallback(
    (event: DragEndEvent): void => {
      endOwnedDrag();
      if (event.over === null || event.over.id === event.active.id) {
        return;
      }
      reorderRepoGroup({ activeProjectId: String(event.active.id), overProjectId: String(event.over.id) });
    },
    [endOwnedDrag, reorderRepoGroup],
  );

  // dnd-kit does not fire onDragCancel when its context unmounts (see
  // PanelDndProvider), and collapsing the sidebar renders null below — the
  // component itself stays mounted, so an unmount-only cleanup would not run.
  // Without this release a drag stranded by the collapse holds the shared drag
  // count forever, silently disabling the hover peek.
  useEffect(() => {
    if (isCollapsed) {
      return undefined;
    }
    return endOwnedDrag;
  }, [isCollapsed, endOwnedDrag]);

  // JSX and rendering logic
  if (isCollapsed) {
    return null;
  }

  return (
    // The sidebar is dense with tooltip triggers, and the tooltip primitive's
    // default skip-delay shows every SUBSEQUENT tooltip instantly while the
    // pointer roams — a hover across the nav lights up a trail of tooltips.
    // Scope a provider over the sidebar: a longer initial delay and no
    // skip-delay chaining, so tooltips only appear on a deliberate hover.
    // (Themes' <Tooltip> reads this provider — `radix-ui` is pinned to the
    // same instance @radix-ui/themes resolves.)
    <TooltipPrimitive.Provider delayDuration={1000} skipDelayDuration={0}>
      <aside
        className={styles.sidebar}
        style={{ width: `${width}px` }}
        data-testid={ElementIds.WORKSPACE_SIDEBAR}
        data-sidebar-drag-active={isSidebarDragActive ? "true" : undefined}
      >
        {/* Window-controls gutter clears the macOS traffic lights, then the
          collapse toggle. */}
        <div className={styles.windowControls} style={{ paddingLeft: getTitleBarLeftPadding(true) }}>
          <Tooltip content="Collapse sidebar" side="right">
            <IconButton
              variant="ghost"
              size="1"
              color="gray"
              className={styles.noDrag}
              onClick={() => setCollapsed(true)}
              aria-label="Collapse sidebar"
              data-testid={ElementIds.SIDEBAR_COLLAPSE_TOGGLE}
            >
              <PanelLeftClose size={16} />
            </IconButton>
          </Tooltip>
        </div>

        <nav className={styles.topActions}>
          <NavItem
            icon={Home}
            label="Home"
            isActive={isHomeRoute}
            onClick={handleOpenHome}
            testId={ElementIds.SIDEBAR_HOME_LINK}
          />
          <NavItem
            icon={Command}
            label="Commands"
            onClick={toggleCommandPalette}
            testId={ElementIds.SIDEBAR_CMDK_LINK}
          />
          {/* Opens the new-workspace dialog; the per-repo "+" in the repo groups
            below is the direct-create affordance. */}
          <NavItem
            icon={Plus}
            label="New Workspace"
            onClick={() => setNewWorkspaceModal({ open: true })}
            testId={ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON}
          />
        </nav>

        <div className={styles.repoList}>
          {/* One group per repo, including repos with no workspaces yet (they show
            a "No workspaces yet" hint). Empty until the first repo is added via the
            "Add repo" button in the bottom actions. */}
          <DndContext
            sensors={groupDndSensors}
            collisionDetection={closestCenter}
            modifiers={sidebarDndModifiers}
            onDragStart={beginOwnedDrag}
            onDragEnd={handleGroupDragEnd}
            onDragCancel={endOwnedDrag}
          >
            <SortableContext items={repoGroups.map((group) => group.projectId)} strategy={verticalListSortingStrategy}>
              {repoGroups.map((group) => (
                <SidebarRepoGroup
                  key={group.projectId}
                  group={group}
                  actions={workspaceActions}
                  openInRuntime={openInRuntime}
                  onWorkspaceClick={handleWorkspaceClick}
                  onWorkspaceHover={handleWorkspaceHover}
                  onBeginDelete={setDeleteTarget}
                />
              ))}
            </SortableContext>
          </DndContext>
        </div>

        <div className={styles.spacer} />

        <nav className={styles.bottomActions}>
          {/* Grouped with the other global actions rather than the per-workspace
            top nav. Always enabled — unlike New Workspace, registering a repo is
            exactly what the user does before any workspace exists, so it stays
            active in the first-run state too. */}
          <NavItem
            icon={Plus}
            label="Add repo"
            onClick={() => setIsAddRepoDialogOpen(true)}
            testId={ElementIds.SIDEBAR_ADD_REPO_BUTTON}
          />
          {/* Opens the Layouts switcher for the current workspace. Disabled off a
            workspace route, where there is no arrangement to switch. */}
          <NavItem
            icon={PanelsTopLeft}
            label="Layouts"
            disabled={!isWorkspaceRoute}
            disabledTooltip="Open a workspace to switch layouts"
            onClick={() => setLayoutsSwitcherOpen(true)}
            testId={ElementIds.SIDEBAR_LAYOUTS_LINK}
          />
          <NavItem
            icon={Settings}
            label="Settings"
            isActive={isSettingsRoute}
            onClick={handleOpenSettings}
            testId={ElementIds.SIDEBAR_SETTINGS_LINK}
          />
          <ReportProblemPopover>
            <button
              type="button"
              className={navItemStyles.navItem}
              aria-label="Report a bug"
              data-testid={ElementIds.SIDEBAR_REPORT_BUG}
            >
              <Bug size={16} className={navItemStyles.navIcon} />
              <span className={navItemStyles.navLabel}>Report a bug</span>
            </button>
          </ReportProblemPopover>
          <div className={styles.versionRow} data-testid={ElementIds.SIDEBAR_VERSION}>
            <VersionPopover />
            <DevModeIndicator />
          </div>
        </nav>

        <ResizeHandle
          axis="x"
          direction={1}
          variant="edge-overlay"
          getSize={() => width}
          onResize={handleResize}
          ariaLabel="Resize sidebar"
          ariaValueNow={Math.round(width)}
          ariaValueMin={MIN_SIDEBAR_WIDTH_PX}
          data-testid={ElementIds.SIDEBAR_RESIZE_HANDLE}
        />

        {/* Hover peek popover shared across rows (anchored beside the hovered row). */}
        <WorkspacePeekOverlay onNavigate={handlePeekNavigate} />

        {/* Destructive workspace delete is confirmed before the optimistic removal. */}
        <DeleteConfirmationDialog
          isOpen={deleteTarget !== null}
          onOpenChange={(open) => {
            if (!open) setDeleteTarget(null);
          }}
          entityType="workspace"
          entityName={deleteTarget?.description ?? ""}
          onConfirm={handleDeleteConfirm}
        />

        {/* The "Add repo" nav button opens the standard add-repo dialog. */}
        <AddRepoDialog open={isAddRepoDialogOpen} onOpenChange={setIsAddRepoDialogOpen} setToast={setAddRepoToast} />
        <Toast
          open={addRepoToast !== null}
          onOpenChange={(open) => !open && setAddRepoToast(null)}
          title={addRepoToast?.title}
          type={addRepoToast?.type}
        />
      </aside>
    </TooltipPrimitive.Provider>
  );
};
