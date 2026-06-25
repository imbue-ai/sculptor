// The app-wide route shell: the global WorkspaceSidebar as the left rail and the
// route Outlet in the content area to its right. It hosts EVERY in-app destination —
// the workspace route (whose Outlet renders WorkspacePage's header + sections), Home,
// and Settings — so the sidebar + cross-cutting chrome stay continuously mounted as
// the user moves between them (no tear-down, no top-bar/tab-strip).
//
// It mounts the cross-cutting survivors the old PageLayout provided — the unified data
// stream, command palette, keyboard shortcuts, plugins, dialogs, and toasts. This is
// the strangler replacement for PageLayout (now removed): nothing here is
// workspace-specific, so the same shell backs Home and Settings.

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
import { usePageLayoutKeyboardShortcuts } from "~/layouts/hooks/usePageLayoutKeyboardShortcuts.ts";
import { PluginLoader } from "~/plugins/PluginLoader.tsx";
import { PluginOverlays } from "~/plugins/PluginOverlays.tsx";

// Error toasts linger longer than the default so the user can read and act on the
// failure before it auto-dismisses.
const ERROR_TOAST_DURATION_MS = 10_000;

export const AppShell = (): ReactElement => {
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
