import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useRef, useState } from "react";

import { HOME_PROMPT_PREFILL } from "~/components/newWorkspace/homePromptPrefill.ts";
import {
  newWorkspaceModalAtom,
  shouldOfferFirstRunWorkspaceAtom,
} from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { pluginHomeViewsAtom } from "~/plugins/pluginRegistry.ts";

import { useIsMobile } from "../../common/hooks/useLayoutMode.ts";
import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import { RecentWorkspaces } from "../add-workspace/components/RecentWorkspaces.tsx";
import { WorkspaceDrawer } from "../workspace/mobile/WorkspaceDrawer.tsx";
import styles from "./HomePage.module.scss";
import { BUILTIN_HOME_VIEW_ID, effectiveHomeViewIdAtom, homeViewOptionsAtom } from "./homeViews.ts";
import { HomeViewSwitcher } from "./HomeViewSwitcher.tsx";
import { MobileHomeHeader } from "./MobileHomeHeader.tsx";
import { RecentWorkspacesHomeView } from "./RecentWorkspacesHomeView.tsx";

export const HomePage = (): ReactElement => {
  const isMobile = useIsMobile();

  // Mobile Home state: its own ☰ header + drawer over the recent-workspaces list.
  // (Mobile does not yet surface the pluggable home-view switcher below.)
  const { handleWorkspaceClick, handleOpenInNewTab } = useWorkspaceNavigation();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // Desktop Home state: the pluggable home-view switcher + selected view.
  const options = useAtomValue(homeViewOptionsAtom);
  const effectiveId = useAtomValue(effectiveHomeViewIdAtom);
  const pluginHomeViews = useAtomValue(pluginHomeViewsAtom);
  const shouldOfferFirstRunWorkspace = useAtomValue(shouldOfferFirstRunWorkspaceAtom);
  const setNewWorkspaceModal = useSetAtom(newWorkspaceModalAtom);

  // First-run create affordance: on a boot with no workspaces, Home's default
  // state is the create dialog itself — an ordinary modal open, dismiss and
  // reopen like any other — prefilled with the /sculptor:help onboarding
  // prompt. The prefill lives HERE, in the visible and editable prompt field,
  // so what the user sees is exactly what their first agent receives — the
  // backend never authors messages on the user's behalf.
  // `shouldOfferFirstRunWorkspaceAtom` stays false while the list is loading,
  // so a boot with existing workspaces never flashes it (the offer trails the
  // stream's first snapshot), and it latches false forever once any workspace
  // has existed this session — deleting the last workspace lands on a plain
  // empty Home, not a surprise modal. An already-open dialog wins over the
  // offer: the user may have opened it during the load window (Cmd/Meta+T, a
  // repo's "+" fallback), and replacing their open request would drop its
  // preset repo — remounting the form and discarding anything typed.
  useEffect(() => {
    if (shouldOfferFirstRunWorkspace) {
      setNewWorkspaceModal((prev) => (prev.open ? prev : { open: true, initialPrompt: HOME_PROMPT_PREFILL }));
    }
  }, [shouldOfferFirstRunWorkspace, setNewWorkspaceModal]);

  // On mobile the global chrome (sidebar rail) is suppressed (see AppShell):
  // Home carries its own header with a ☰ that opens the same drawer
  // (Home / Settings / workspaces) as the Workspace view, keeping the
  // recent-workspaces body below it. The first-run effect above still runs —
  // the shared new-workspace modal is mobile's creation path too.
  if (isMobile) {
    const recentWorkspaces = (
      <RecentWorkspaces
        searchInputRef={searchInputRef}
        autoFocusSearch={false}
        onWorkspaceClick={handleWorkspaceClick}
        onOpenInNewTab={handleOpenInNewTab}
        onEscapeToTitle={(): void => {
          searchInputRef.current?.focus();
        }}
      />
    );
    return (
      <div className={`mobileTheme ${styles.mobileShell}`}>
        <MobileHomeHeader onOpenDrawer={() => setIsDrawerOpen(true)} />
        <div className={styles.mobileContent}>{recentWorkspaces}</div>

        <div
          className={`${styles.backdrop} ${isDrawerOpen ? styles.open : ""}`}
          onClick={() => setIsDrawerOpen(false)}
          aria-hidden={!isDrawerOpen}
        />
        <WorkspaceDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} />
      </div>
    );
  }

  // Only surface the switcher once there is something to switch to: with no
  // plugin home views the page is the recent-workspaces list, exactly as before.
  const shouldShowSwitcher = options.length > 1;

  const SelectedView =
    effectiveId === BUILTIN_HOME_VIEW_ID
      ? RecentWorkspacesHomeView
      : (pluginHomeViews.find((view) => view.id === effectiveId)?.component ?? RecentWorkspacesHomeView);

  return (
    <div className={styles.root}>
      {shouldShowSwitcher && (
        <div className={styles.switcherBar}>
          <HomeViewSwitcher />
        </div>
      )}
      <div className={styles.body}>
        <SelectedView />
      </div>
    </div>
  );
};
