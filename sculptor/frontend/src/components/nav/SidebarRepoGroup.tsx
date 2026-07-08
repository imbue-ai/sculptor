// One collapsible repo group in the workspace sidebar: the repo header row (collapse
// chevron, hover-revealed repository settings, and an always-visible "+" that
// direct-creates a workspace in this repo, falling back to the new-workspace dialog
// pre-scoped to the repo when the branch can't be resolved or the create fails),
// followed by the repo's children while expanded. With workspace groups enabled the
// children are the repo's group cards (creation order) above the loose workspace
// rows (stored drag order); with the flag off they are exactly the workspace rows.
// Cross-group concerns — building the groups, the shared action list, and the delete
// confirmation — stay in WorkspaceSidebar and arrive as props; per-group state
// (collapse, rename) is read from its atoms here.
//
// The group is itself a sortable item of WorkspaceSidebar's repo-group DndContext
// (dragged by its header), and it hosts its OWN DndContext for its workspace rows —
// a workspace belongs to its repo, so scoping the row context per group makes
// cross-repo drops structurally impossible rather than merely rejected.

import type { DragEndEvent } from "@dnd-kit/core";
import { closestCenter, DndContext } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { atom, useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import { ChevronDown, ChevronRight, Plus, Settings } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef } from "react";

import type { Workspace, WorkspaceGroup } from "~/api";
import { ElementIds, updateWorkspace } from "~/api";
import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { workspaceRenameErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { isWorkspaceGroupsEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { workspaceGroupsForProjectAtomFamily } from "~/common/state/atoms/workspaceGroups.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { renamingWorkspaceIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import type { OpenInRuntime } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceAction } from "~/components/CommandPalette/contextActions/types.ts";
import { useCreateWorkspaceFromSidebar } from "~/components/newWorkspace/useCreateWorkspaceFromSidebar.ts";
import { ToastType } from "~/components/Toast.tsx";

import { adjustSidebarDragCountAtom, collapsedRepoGroupsAtom, isRepoCollapsedAtomFamily } from "./navAtoms.ts";
import { sidebarDndModifiers, useSidebarDndSensors } from "./sidebarDnd.ts";
import styles from "./SidebarRepoGroup.module.scss";
import type { RepoGroup } from "./sidebarWorkspaceOrder.ts";
import { reorderSidebarWorkspaceAtom } from "./sidebarWorkspaceOrder.ts";
import { SidebarWorkspaceRow } from "./SidebarWorkspaceRow.tsx";
import { WorkspaceGroupCard } from "./WorkspaceGroupCard.tsx";
import { composeRepoSectionChildren } from "./workspaceGroupComposition.ts";

// What the workspace-groups flag gates off subscribes to instead of the group
// store: with the flag disabled the render path must not touch group atoms at
// all, so the section renders exactly the pre-groups tree.
const NO_WORKSPACE_GROUPS_ATOM = atom<ReadonlyArray<WorkspaceGroup>>([]);

type SidebarRepoGroupProps = {
  group: RepoGroup;
  // The shared workspace action list (rename/delete/git/open-in), built once in
  // WorkspaceSidebar so every group and the command palette agree on the entries.
  actions: ReadonlyArray<WorkspaceAction>;
  openInRuntime: OpenInRuntime;
  // Whether to render the per-repo header actions (settings gear + direct-create
  // "+"). Suppressed on the first-run page: that page doesn't mount AppShell, so
  // the "+"'s dialog fallback and its error toast wouldn't render — the inline
  // first-run form is the only create affordance while the workspace list is empty.
  showActions: boolean;
  onWorkspaceClick: (workspaceId: string) => void;
  onWorkspaceHover: (workspaceId: string) => void;
  // Delete is confirmed by a dialog owned by WorkspaceSidebar (shared across
  // groups), so beginning one hands the target back up.
  onBeginDelete: (workspace: Workspace) => void;
};

export const SidebarRepoGroup = ({
  group,
  actions,
  openInRuntime,
  showActions,
  onWorkspaceClick,
  onWorkspaceHover,
  onBeginDelete,
}: SidebarRepoGroupProps): ReactElement => {
  // External atoms
  const isRepoCollapsed = useAtomValue(isRepoCollapsedAtomFamily(group.projectId));
  const setCollapsedRepos = useSetAtom(collapsedRepoGroupsAtom);
  const setRenameErrorToast = useSetAtom(workspaceRenameErrorToastAtom);
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();
  const adjustDragCount = useSetAtom(adjustSidebarDragCountAtom);
  const reorderWorkspace = useSetAtom(reorderSidebarWorkspaceAtom);
  const store = useStore();
  const areWorkspaceGroupsEnabled = useAtomValue(isWorkspaceGroupsEnabledAtom);
  const workspaceGroups = useAtomValue(
    areWorkspaceGroupsEnabled ? workspaceGroupsForProjectAtomFamily(group.projectId) : NO_WORKSPACE_GROUPS_ATOM,
  );

  // Whether the in-flight sidebar drag was started by THIS group's row context.
  // Every drag context adjusts the shared drag count, so end/cancel/cleanup must
  // only decrement for a drag they own — an unowning cleanup (collapsing a
  // different group mid-drag) would otherwise release another context's drag.
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

  // External hooks
  const openSettings = useOpenSettings();
  const { workspaceId: activeWorkspaceId } = useImbueLocation();
  const dangerColor = useThemeDangerColor();

  // The group is a sortable item of WorkspaceSidebar's repo-group context: the
  // whole group (header + rows) is the measured node so its rows travel with it,
  // and the header button is the drag activator.
  const {
    attributes: groupAttributes,
    listeners: groupListeners,
    setNodeRef: setGroupNodeRef,
    setActivatorNodeRef: setGroupActivatorNodeRef,
    transform: groupTransform,
    transition: groupTransition,
    isDragging: isGroupDragging,
    isOver: isGroupOver,
  } = useSortable({ id: group.projectId });

  // The rows' own drag context; see the module comment for why it lives per group.
  const rowDndSensors = useSidebarDndSensors();

  // Functions and callbacks
  const handleToggleCollapsed = (): void => {
    setCollapsedRepos((prev) => ({ ...prev, [group.projectId]: !(prev[group.projectId] ?? false) }));
  };

  // Enter toggles collapse from the keyboard, like a click; every other key falls
  // through to the dnd-kit keyboard sensor so Space picks the group up (see the
  // matching handler on SidebarWorkspaceRow).
  const handleHeaderKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter" && event.target === event.currentTarget && !isGroupDragging) {
      event.preventDefault();
      handleToggleCollapsed();
      return;
    }
    groupListeners?.onKeyDown?.(event);
  };

  const handleRowDragEnd = useCallback(
    (event: DragEndEvent): void => {
      endOwnedDrag();
      if (event.over === null || event.over.id === event.active.id) {
        return;
      }
      reorderWorkspace({
        projectId: group.projectId,
        activeWorkspaceId: String(event.active.id),
        overWorkspaceId: String(event.over.id),
      });
    },
    [endOwnedDrag, reorderWorkspace, group.projectId],
  );

  // dnd-kit does not fire onDragCancel when its context unmounts (see
  // PanelDndProvider), and the rows' context unmounts whenever the group
  // collapses — which can happen mid-drag (a keyboard drag is parked while the
  // header stays clickable). Without this release a stranded drag leaves the
  // shared drag count held forever, silently disabling the hover peek.
  useEffect(() => {
    if (isRepoCollapsed) {
      return undefined;
    }
    return endOwnedDrag;
  }, [isRepoCollapsed, endOwnedDrag]);

  // Reference-stable (the rows are memoized on their props): the rename
  // callbacks depend only on reference-stable atom setters and the store.
  const handleRenameCommit = useCallback(
    (workspaceId: string, newName: string): void => {
      setRenamingWorkspaceId(null);
      const workspaceAtom = workspaceAtomFamily(workspaceId);
      const previous = store.get(workspaceAtom);
      // Optimistically show the new name and let the WebSocket frame reconcile
      // with the server-authoritative value; roll back and surface a toast if the
      // write is rejected so the rename never fails silently.
      if (previous !== null) {
        store.set(workspaceAtom, { ...previous, description: newName });
      }
      updateWorkspace({
        path: { workspace_id: workspaceId },
        body: { description: newName },
      }).catch((error: unknown) => {
        console.error("Failed to rename workspace:", error);
        if (previous !== null) {
          store.set(workspaceAtom, previous);
        }
        setRenameErrorToast({
          title: `Failed to rename "${previous?.description ?? "workspace"}"`,
          description: "The name has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: null,
        });
      });
    },
    [setRenamingWorkspaceId, setRenameErrorToast, store],
  );

  const handleRenameCancel = useCallback((): void => {
    setRenamingWorkspaceId(null);
  }, [setRenamingWorkspaceId]);

  // JSX and rendering logic
  const Chevron = isRepoCollapsed ? ChevronRight : ChevronDown;

  // The section's children while expanded: workspace-group cards first, then the
  // loose rows. This interim placement (groups-above-loose) is the composition
  // seam the sidebar-order lane extends when group cards join the manual drag
  // ordering; keep any placement logic here.
  const { groupsWithMembers, looseWorkspaces } = useMemo(
    () => composeRepoSectionChildren(group.workspaces, workspaceGroups),
    [group.workspaces, workspaceGroups],
  );

  return (
    <div
      ref={setGroupNodeRef}
      className={`${styles.repoGroup} ${isGroupDragging ? styles.rowDragging : ""}`}
      style={{ transform: CSS.Translate.toString(groupTransform), transition: groupTransition }}
    >
      <div className={styles.repoHeader}>
        <button
          type="button"
          ref={setGroupActivatorNodeRef}
          className={styles.repoHeaderButton}
          {...groupAttributes}
          {...groupListeners}
          // After the listeners spread so this composed handler REPLACES the
          // sensor's raw onKeyDown (it delegates every non-Enter key back to it).
          onKeyDown={handleHeaderKeyDown}
          onClick={handleToggleCollapsed}
          data-testid={ElementIds.SIDEBAR_REPO_GROUP}
          data-project-id={group.projectId}
          data-sidebar-dragging={isGroupDragging ? "true" : undefined}
          data-sidebar-drop-target={isGroupOver && !isGroupDragging ? "true" : undefined}
        >
          <Chevron size={16} className={styles.repoChevron} />
          <Text className={styles.repoName} truncate>
            {group.name}
          </Text>
        </button>
        {showActions && (
          <Flex className={styles.rowActions} gap="2">
            <Tooltip content="Repository settings" side="right">
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                className={styles.hoverReveal}
                onClick={() => openSettings("REPOSITORIES", group.projectId)}
                aria-label="Repository settings"
                data-testid={ElementIds.SIDEBAR_REPO_SETTINGS}
                data-project-id={group.projectId}
              >
                <Settings size={13} />
              </IconButton>
            </Tooltip>
            <Tooltip content="New workspace in this repo" side="right">
              {/* Direct-create in THIS repo (fresh auto branch, last-used or
                  default settings); failures fall back to the dialog
                  pre-selecting the repo. The nav "New Workspace" above is the
                  open-the-dialog affordance. */}
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                disabled={isCreating}
                onClick={() => void createFromSidebar(group.projectId)}
                aria-label="New workspace in this repo"
                data-testid={ElementIds.SIDEBAR_REPO_ADD_WORKSPACE}
                data-project-id={group.projectId}
              >
                <Plus size={13} />
              </IconButton>
            </Tooltip>
          </Flex>
        )}
      </div>
      {!isRepoCollapsed && group.workspaces.length === 0 && (
        <Text className={styles.noWorkspacesHint} data-testid={ElementIds.SIDEBAR_NO_WORKSPACES_HINT}>
          No workspaces yet
        </Text>
      )}
      {!isRepoCollapsed &&
        groupsWithMembers.map(({ group: workspaceGroup, members }) => (
          <WorkspaceGroupCard
            key={workspaceGroup.objectId}
            group={workspaceGroup}
            members={members}
            actions={actions}
            openInRuntime={openInRuntime}
            destructiveColor={dangerColor}
            renamingWorkspaceId={renamingWorkspaceId}
            activeWorkspaceId={activeWorkspaceId}
            onWorkspaceClick={onWorkspaceClick}
            onWorkspaceHover={onWorkspaceHover}
            onWorkspaceRenameCommit={handleRenameCommit}
            onWorkspaceRenameCancel={handleRenameCancel}
            onBeginDelete={onBeginDelete}
          />
        ))}
      {!isRepoCollapsed && looseWorkspaces.length > 0 && (
        // The rows get their own container (rather than sitting directly in the
        // group) so restrictToParentElement clamps a dragged row to the rows'
        // extent — it can slide between its siblings but never up over the
        // group header or the group cards above.
        <div className={styles.repoRows}>
          <DndContext
            sensors={rowDndSensors}
            collisionDetection={closestCenter}
            modifiers={sidebarDndModifiers}
            onDragStart={beginOwnedDrag}
            onDragEnd={handleRowDragEnd}
            onDragCancel={endOwnedDrag}
          >
            <SortableContext items={looseWorkspaces.map((ws) => ws.objectId)} strategy={verticalListSortingStrategy}>
              {looseWorkspaces.map((ws) => (
                <SidebarWorkspaceRow
                  key={ws.objectId}
                  workspace={ws}
                  isRenaming={renamingWorkspaceId === ws.objectId}
                  isActive={ws.objectId === activeWorkspaceId}
                  actions={actions}
                  openInRuntime={openInRuntime}
                  destructiveColor={dangerColor}
                  onNavigate={onWorkspaceClick}
                  onHover={onWorkspaceHover}
                  onRenameCommit={handleRenameCommit}
                  onRenameCancel={handleRenameCancel}
                  onBeginDelete={onBeginDelete}
                />
              ))}
            </SortableContext>
          </DndContext>
        </div>
      )}
    </div>
  );
};
