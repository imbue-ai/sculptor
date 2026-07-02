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
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useState } from "react";
import { Outlet } from "react-router-dom";

import { useSyncActiveTabFromRoute } from "~/common/hooks/useSyncActiveTabFromRoute.ts";
import { useActiveProjectID } from "~/common/NavigateUtils.ts";
import { backendStatusAtom } from "~/common/state/atoms/backend.ts";
import {
  createAgentErrorToastAtom,
  deleteErrorToastAtom,
  mentionChipUnreachableToastAtom,
  terminalPromptRejectedToastAtom,
  workspaceDeleteErrorToastAtom,
  workspaceOpenCloseErrorToastAtom,
} from "~/common/state/atoms/toasts.ts";
import { useProject } from "~/common/state/hooks/useProjects.ts";
import { useUnifiedStream } from "~/common/state/hooks/useUnifiedStream";
import type { AtomToastAtom } from "~/components/AtomToast.tsx";
import { AtomToast } from "~/components/AtomToast.tsx";
import { CommandPalette } from "~/components/CommandPalette";
import { CommandRegistrations } from "~/components/CommandPalette/CommandRegistrations.tsx";
import { KeyboardShortcutsDialog } from "~/components/KeyboardShortcutsDialog.tsx";
import { sidebarCollapsedAtom } from "~/components/layout/sidebarAtoms.ts";
import { CollapsedSidebarToggle } from "~/components/nav/CollapsedSidebarToggle.tsx";
import { WorkspaceSidebar } from "~/components/nav/WorkspaceSidebar.tsx";
import { NewWorkspaceModal } from "~/components/newWorkspace/NewWorkspaceModal.tsx";
import { NotificationToasts } from "~/components/NotificationToasts.tsx";
import { RepoPathDialog } from "~/components/RepoPathDialog.tsx";
import { WarningStatusBanner } from "~/components/WarningStatusBanner.tsx";
import { usePageLayoutKeyboardShortcuts } from "~/layouts/hooks/usePageLayoutKeyboardShortcuts.ts";
import { PluginLoader } from "~/plugins/PluginLoader.tsx";
import { PluginOverlays } from "~/plugins/PluginOverlays.tsx";

// Error toasts linger longer than the default so the user can read and act on the
// failure before it auto-dismisses.
const ERROR_TOAST_DURATION_MS = 10_000;

// The app-level toasts, one <AtomToast> per atom: setting an atom anywhere in the
// app pops the toast here, and closing it clears the atom. Variant styling and
// action buttons (e.g. the delete-error Retry) ride along in the atom payload, so
// entries only differ by dismiss duration.
const APP_TOASTS: ReadonlyArray<{ key: string; toastAtom: AtomToastAtom; duration?: number }> = [
  { key: "delete-error", toastAtom: deleteErrorToastAtom, duration: ERROR_TOAST_DURATION_MS },
  { key: "create-agent-error", toastAtom: createAgentErrorToastAtom, duration: ERROR_TOAST_DURATION_MS },
  { key: "workspace-delete-error", toastAtom: workspaceDeleteErrorToastAtom, duration: ERROR_TOAST_DURATION_MS },
  { key: "workspace-open-close-error", toastAtom: workspaceOpenCloseErrorToastAtom, duration: ERROR_TOAST_DURATION_MS },
  { key: "mention-chip-unreachable", toastAtom: mentionChipUnreachableToastAtom },
  { key: "terminal-prompt-rejected", toastAtom: terminalPromptRejectedToastAtom },
];

export const AppShell = (): ReactElement => {
  // External atoms
  const isSidebarCollapsed = useAtomValue(sidebarCollapsedAtom);
  const backendStatus = useAtomValue(backendStatusAtom);

  // Internal state
  const [isRepoPathDialogOpen, setIsRepoPathDialogOpen] = useState<boolean>(false);

  // External hooks
  const projectID = useActiveProjectID();
  const currentProject = useProject(projectID ?? "");

  useUnifiedStream();
  usePageLayoutKeyboardShortcuts();
  useSyncActiveTabFromRoute();

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
      {APP_TOASTS.map(({ key, toastAtom, duration }) => (
        <AtomToast key={key} toastAtom={toastAtom} duration={duration} />
      ))}
    </>
  );
};
