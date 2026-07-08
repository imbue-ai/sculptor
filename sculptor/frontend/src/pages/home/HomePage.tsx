import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { HOME_PROMPT_PREFILL } from "~/components/newWorkspace/homePromptPrefill.ts";
import { isWorkspaceListEmptyAtom, newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { pluginHomeViewsAtom } from "~/plugins/pluginRegistry.ts";

import styles from "./HomePage.module.scss";
import { BUILTIN_HOME_VIEW_ID, effectiveHomeViewIdAtom, homeViewOptionsAtom } from "./homeViews.ts";
import { HomeViewSwitcher } from "./HomeViewSwitcher.tsx";
import { RecentWorkspacesHomeView } from "./RecentWorkspacesHomeView.tsx";

export const HomePage = (): ReactElement => {
  const options = useAtomValue(homeViewOptionsAtom);
  const effectiveId = useAtomValue(effectiveHomeViewIdAtom);
  const pluginHomeViews = useAtomValue(pluginHomeViewsAtom);
  const isWorkspaceListEmpty = useAtomValue(isWorkspaceListEmptyAtom);
  const setNewWorkspaceModal = useSetAtom(newWorkspaceModalAtom);

  // First-run create affordance: with no workspaces yet, Home's default state
  // is the create dialog itself — an ordinary modal open, dismiss and reopen
  // like any other — prefilled with the /sculptor:help onboarding prompt.
  // The prefill lives HERE, in the visible and editable prompt field, so what
  // the user sees is exactly what their first agent receives — the backend
  // never authors messages on the user's behalf.
  // `isWorkspaceListEmptyAtom` stays false while the list is loading, so a
  // boot with existing workspaces never flashes it; the offer therefore
  // trails the stream's first snapshot. An already-open dialog wins over the
  // offer: the user may have opened it during the load window (Cmd/Meta+T, a
  // repo's "+" fallback), and replacing their open request would drop its
  // preset repo — remounting the form and discarding anything typed.
  useEffect(() => {
    if (isWorkspaceListEmpty) {
      setNewWorkspaceModal((prev) => (prev.open ? prev : { open: true, initialPrompt: HOME_PROMPT_PREFILL }));
    }
  }, [isWorkspaceListEmpty, setNewWorkspaceModal]);

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
