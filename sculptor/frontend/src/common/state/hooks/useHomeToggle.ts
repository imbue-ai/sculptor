import { useAtomValue } from "jotai";
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import {
  effectiveOpenTabIdsAtom,
  lastNonHomeLocationAtom,
  NEW_WORKSPACE_TAB_PREFIX,
} from "~/common/state/atoms/workspaces.ts";
import { HOME_TAB_ID } from "~/components/workspaceTabIds.ts";

/**
 * A tab id is "visible" if WorkspaceTabs renders a pill for it: real
 * workspace ids, ``__settings__``, and ``__component_gallery__``. The
 * two excluded ids — ``__home__`` and the legacy
 * ``__new_workspace_<draftId>__`` from pre-modal sessions — have no
 * TabDefinition, so a stale entry in tabOrderAtom would be invisible
 * to the user and must not gate a navigation.
 *
 * Note: ``effectiveOpenTabIdsAtom`` already filters out the legacy
 * ``__new_workspace_*__`` IDs upstream, but we re-check here to defend
 * the safety guard against any future caller that bypasses the filter.
 */
const isVisibleTabId = (id: string): boolean => id !== HOME_TAB_ID && !id.startsWith(NEW_WORKSPACE_TAB_PREFIX);

type UseHomeToggle = {
  /** Toggle between `/home` and the most recent non-home pathname. */
  toggleHome: () => void;
  /**
   * True when activating the toggle would do nothing: we're already on
   * `/home` and there's nowhere to go back to (no visible tab, or no
   * remembered non-home location). Surfaced so the Home button can reflect
   * the gate via `aria-disabled` instead of silently swallowing the click.
   */
  isToggleNoOp: boolean;
};

/**
 * Toggle between `/home` and the most recent non-home pathname.
 *
 * On a non-home page: navigates to `/home`. The TopBar's location-
 * tracking effect captures the current path into
 * `lastNonHomeLocationAtom` so we can come back to it later.
 *
 * On `/home`: navigates to that captured pathname — but only when at
 * least one *visible* tab is still open. With zero visible tabs,
 * `lastNonHomeLocation` is almost certainly stale (refers to a
 * workspace the user just closed), and "toggling off" home would
 * route them to a 404 or to a closed-workspace URL. Better to keep
 * them on /home until they open something. Same fallback when we
 * don't have a remembered pathname yet (fresh session that landed
 * on /home with no prior visit).
 *
 * Used by the topbar Home icon click handler AND the global "home"
 * keybinding so both surfaces share one toggle behavior.
 */
export const useHomeToggle = (): UseHomeToggle => {
  const navigate = useNavigate();
  const { navigateToHome } = useImbueNavigate();
  const { isHomeRoute } = useImbueLocation();
  const lastNonHomeLocation = useAtomValue(lastNonHomeLocationAtom);
  const openTabIds = useAtomValue(effectiveOpenTabIdsAtom);

  // `effectiveOpenTabIdsAtom` returns a fresh array on every workspace WS
  // update, so this `.some(...)` re-runs each render — but it's cheap, and
  // reducing to a *primitive boolean* is what keeps `toggleHome`'s useCallback
  // identity stable across those updates: the dep only changes when the
  // boolean value flips, not when the array reference does. That matters
  // because usePageLayoutKeyboardShortcuts captures `toggleHome` in a useEffect
  // dep and we don't want to re-register the global keydown listener every time
  // a tab opens or closes.
  const hasVisibleTab = openTabIds.some(isVisibleTabId);

  // On /home the toggle only navigates when there's a visible tab AND a
  // remembered destination; otherwise it deliberately does nothing (see the
  // callback below). Reflect that so the Home button isn't a silently gated
  // handler.
  const isToggleNoOp = isHomeRoute && (!hasVisibleTab || lastNonHomeLocation === null);

  const toggleHome = useCallback((): void => {
    if (isHomeRoute) {
      if (!hasVisibleTab) return;
      if (lastNonHomeLocation) navigate(lastNonHomeLocation);
      return;
    }
    navigateToHome();
  }, [isHomeRoute, lastNonHomeLocation, hasVisibleTab, navigate, navigateToHome]);

  return { toggleHome, isToggleNoOp };
};
