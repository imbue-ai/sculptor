// The no-workspaces first-run page. When the workspace list is
// genuinely empty, the app gate renders this in place of the normal layouts:
// the sidebar (open) on the left and, in the content area, the new-workspace
// form inline in a card. The first prompt defaults to the existing
// `/sculptor:help` prefill. Navigation is otherwise disabled — only
// this form and Settings are reachable, and Cmd+K / the global shortcuts are
// off, gated by `areGlobalShortcutsDisabledAtom`.
//
// Creating the first workspace navigates to the new agent (handled inside
// `useCreateWorkspace`); that flips `isWorkspaceListEmptyAtom` to false, the
// gate stops rendering this page, and the full workspace page takes over in the
// default state.

import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { ElementIds } from "~/api";
import { CollapsedSidebarToggle } from "~/app/nav/CollapsedSidebarToggle.tsx";
import { WorkspaceSidebar } from "~/app/nav/WorkspaceSidebar.tsx";
import { useUnifiedStream } from "~/common/state/hooks/useUnifiedStream";
import { HOME_PROMPT_PREFILL } from "~/components/newWorkspace/homePromptPrefill.ts";
import { NewWorkspaceForm } from "~/components/newWorkspace/NewWorkspaceForm.tsx";
import { sidebarCollapsedAtom } from "~/pages/workspace/layout/atoms/sidebar.ts";

import styles from "./EmptyFirstRunPage.module.scss";

export const EmptyFirstRunPage = (): ReactElement => {
  const isSidebarCollapsed = useAtomValue(sidebarCollapsedAtom);

  // The normal app shell (AppShell) doesn't mount while
  // this page is showing, so own the websocket stream here. Without it the
  // first created workspace would never arrive and the gate would never flip
  // back to the full workspace page.
  useUnifiedStream();

  // A successful create navigates away (inside `useCreateWorkspace`), so there
  // is nothing for the page to do on completion.
  const handleCreated = useCallback((): void => {}, []);

  return (
    <Flex direction="row" height="var(--app-height)" width="100vw" position="relative" overflow="hidden">
      {/* Sidebar stays open in the empty state; respect a manual collapse by
          offering the expand toggle so the user is never stranded. */}
      {isSidebarCollapsed ? <CollapsedSidebarToggle /> : <WorkspaceSidebar />}

      <Flex
        direction="column"
        align="center"
        flexGrow="1"
        minWidth="0"
        minHeight="0"
        overflow="auto"
        className={styles.content}
        data-testid={ElementIds.EMPTY_FIRST_RUN_PAGE}
      >
        <div className={styles.formCard}>
          <NewWorkspaceForm initialPrompt={HOME_PROMPT_PREFILL} onCreated={handleCreated} />
        </div>
      </Flex>
    </Flex>
  );
};
