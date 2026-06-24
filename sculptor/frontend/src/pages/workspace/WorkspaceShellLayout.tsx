// The route-level chrome host for the workspace route (the strangler cutover of
// the old PageLayout/docking shell). It renders the global WorkspaceSidebar as the
// left rail (component_hierarchy.md → "Top-level tree": the sidebar is global
// chrome) and the route Outlet in the content area to its right. It also mounts the
// cross-cutting survivors that the old PageLayout provided for this route — the
// unified data stream, command palette, keyboard shortcuts, plugins, dialogs, and
// toasts — so swapping the top bar for the sidebar keeps the route at parity.
//
// PageLayout still backs Home / Settings / new-workspace; those routes migrate off
// it later.

import { Flex } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";
import { Outlet } from "react-router-dom";

import { useSyncActiveTabFromRoute } from "~/common/hooks/useSyncActiveTabFromRoute.ts";
import { useActiveProjectID } from "~/common/NavigateUtils.ts";
import { backendStatusAtom } from "~/common/state/atoms/backend.ts";
import {
  deleteErrorToastAtom,
  mentionChipUnreachableToastAtom,
  terminalPromptRejectedToastAtom,
  workspaceDeleteErrorToastAtom,
  workspaceOpenCloseErrorToastAtom,
} from "~/common/state/atoms/toasts.ts";
import { useProject } from "~/common/state/hooks/useProjects.ts";
import { useUnifiedStream } from "~/common/state/hooks/useUnifiedStream";
import { AutoUpdateToasts } from "~/components/AutoUpdateToasts.tsx";
import { CommandPalette } from "~/components/CommandPalette";
import { CommandRegistrations } from "~/components/CommandPalette/CommandRegistrations.tsx";
import { KeyboardShortcutsDialog } from "~/components/KeyboardShortcutsDialog.tsx";
import { sidebarCollapsedAtom } from "~/components/layout/sidebarAtoms.ts";
import { CollapsedSidebarToggle } from "~/components/nav/CollapsedSidebarToggle.tsx";
import { WorkspaceSidebar } from "~/components/nav/WorkspaceSidebar.tsx";
import { NewWorkspaceModal } from "~/components/newWorkspace/NewWorkspaceModal.tsx";
import { NotificationToasts } from "~/components/NotificationToasts.tsx";
import { RepoPathDialog } from "~/components/RepoPathDialog.tsx";
import { Toast } from "~/components/Toast.tsx";
import { WarningStatusBanner } from "~/components/WarningStatusBanner.tsx";
import { useAutoUpdateListener } from "~/hooks/useAutoUpdateListener.ts";
import { usePageLayoutKeyboardShortcuts } from "~/layouts/hooks/usePageLayoutKeyboardShortcuts.ts";
import { PluginLoader } from "~/plugins/PluginLoader.tsx";
import { PluginOverlays } from "~/plugins/PluginOverlays.tsx";

// Error toasts linger longer than the default so the user can read and act on the
// failure before it auto-dismisses.
const ERROR_TOAST_DURATION_MS = 10_000;

export const WorkspaceShellLayout = (): ReactElement => {
  // External atoms
  const isSidebarCollapsed = useAtomValue(sidebarCollapsedAtom);
  const backendStatus = useAtomValue(backendStatusAtom);
  const deleteErrorToast = useAtomValue(deleteErrorToastAtom);
  const setDeleteErrorToast = useSetAtom(deleteErrorToastAtom);
  const workspaceDeleteErrorToast = useAtomValue(workspaceDeleteErrorToastAtom);
  const setWorkspaceDeleteErrorToast = useSetAtom(workspaceDeleteErrorToastAtom);
  const workspaceOpenCloseErrorToast = useAtomValue(workspaceOpenCloseErrorToastAtom);
  const setWorkspaceOpenCloseErrorToast = useSetAtom(workspaceOpenCloseErrorToastAtom);
  const mentionChipUnreachableToast = useAtomValue(mentionChipUnreachableToastAtom);
  const setMentionChipUnreachableToast = useSetAtom(mentionChipUnreachableToastAtom);
  const terminalPromptRejectedToast = useAtomValue(terminalPromptRejectedToastAtom);
  const setTerminalPromptRejectedToast = useSetAtom(terminalPromptRejectedToastAtom);

  // Internal state
  const [isRepoPathDialogOpen, setIsRepoPathDialogOpen] = useState<boolean>(false);

  // External hooks
  const projectID = useActiveProjectID();
  const currentProject = useProject(projectID ?? "");

  useUnifiedStream();
  usePageLayoutKeyboardShortcuts();
  useAutoUpdateListener();
  useSyncActiveTabFromRoute();

  // Functions and callbacks
  // Stable callbacks so the memoized <Toast> instances bail out instead of
  // re-rendering on every unrelated commit while they sit closed.
  const handleDeleteErrorOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) setDeleteErrorToast(null);
    },
    [setDeleteErrorToast],
  );
  const handleWorkspaceDeleteErrorOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) setWorkspaceDeleteErrorToast(null);
    },
    [setWorkspaceDeleteErrorToast],
  );
  const handleWorkspaceOpenCloseErrorOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) setWorkspaceOpenCloseErrorToast(null);
    },
    [setWorkspaceOpenCloseErrorToast],
  );
  const handleMentionChipUnreachableOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) setMentionChipUnreachableToast(null);
    },
    [setMentionChipUnreachableToast],
  );
  const handleTerminalPromptRejectedOpenChange = useCallback(
    (open: boolean): void => {
      if (!open) setTerminalPromptRejectedToast(null);
    },
    [setTerminalPromptRejectedToast],
  );

  // JSX and rendering logic
  const hasBackendStopped = backendStatus.status === "unresponsive";
  const hasHealthWarningOnBackend = backendStatus.status === "warning";
  const isProjectPathInaccessible = currentProject !== null && currentProject.isPathAccessible === false;

  return (
    <>
      <Flex direction="row" height="var(--app-height)" width="100vw" position="relative" overflow="hidden">
        {/* Global chrome: the sidebar rail (or the collapsed expand toggle). */}
        {isSidebarCollapsed ? <CollapsedSidebarToggle /> : <WorkspaceSidebar />}

        <Flex
          direction="column"
          flexGrow="1"
          minWidth="0"
          minHeight="0"
          position="relative"
          overflow="hidden"
          style={{ background: "var(--gray-2)" }}
        >
          <PluginLoader />
          <PluginOverlays />
          <Outlet />
          {isProjectPathInaccessible && currentProject !== null && (
            <WarningStatusBanner
              message={`Project folder not found: ${currentProject.name}.`}
              linkText="Learn more"
              onLinkClick={() => setIsRepoPathDialogOpen(true)}
            />
          )}
          {(hasBackendStopped || hasHealthWarningOnBackend) && (
            <WarningStatusBanner message={backendStatus.payload.message} />
          )}
        </Flex>
      </Flex>

      <CommandRegistrations />
      <CommandPalette />
      <KeyboardShortcutsDialog />
      <NewWorkspaceModal />
      <RepoPathDialog
        isOpen={isRepoPathDialogOpen}
        project={currentProject}
        onClose={() => setIsRepoPathDialogOpen(false)}
      />
      <NotificationToasts />
      <AutoUpdateToasts />
      <Toast
        open={deleteErrorToast !== null}
        onOpenChange={handleDeleteErrorOpenChange}
        title={deleteErrorToast?.title}
        description={deleteErrorToast?.description}
        type={deleteErrorToast?.type}
        action={deleteErrorToast?.action ?? undefined}
        duration={ERROR_TOAST_DURATION_MS}
      />
      <Toast
        open={workspaceDeleteErrorToast !== null}
        onOpenChange={handleWorkspaceDeleteErrorOpenChange}
        title={workspaceDeleteErrorToast?.title}
        description={workspaceDeleteErrorToast?.description}
        type={workspaceDeleteErrorToast?.type}
        action={workspaceDeleteErrorToast?.action ?? undefined}
        duration={ERROR_TOAST_DURATION_MS}
      />
      <Toast
        open={workspaceOpenCloseErrorToast !== null}
        onOpenChange={handleWorkspaceOpenCloseErrorOpenChange}
        title={workspaceOpenCloseErrorToast?.title}
        description={workspaceOpenCloseErrorToast?.description}
        type={workspaceOpenCloseErrorToast?.type}
        action={workspaceOpenCloseErrorToast?.action ?? undefined}
        duration={ERROR_TOAST_DURATION_MS}
      />
      <Toast
        open={mentionChipUnreachableToast !== null}
        onOpenChange={handleMentionChipUnreachableOpenChange}
        title={mentionChipUnreachableToast?.title}
        description={mentionChipUnreachableToast?.description}
      />
      <Toast
        open={terminalPromptRejectedToast !== null}
        onOpenChange={handleTerminalPromptRejectedOpenChange}
        title={terminalPromptRejectedToast?.title}
        description={terminalPromptRejectedToast?.description}
      />
    </>
  );
};
