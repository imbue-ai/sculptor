import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";
import type { ComponentType } from "react";

import { pluginHomeViewsAtom } from "~/plugins/pluginRegistry.ts";

/**
 * Reserved id of the built-in homepage view (the recent-workspaces list). It is
 * always the first option and the fallback whenever the persisted selection
 * names a view that is not currently registered.
 */
export const BUILTIN_HOME_VIEW_ID = "recent-workspaces";

const BUILTIN_HOME_VIEW_TITLE = "Recent workspaces";

/** A switcher entry: the built-in view plus one per registered plugin home view. */
export type HomeViewOption = {
  id: string;
  title: string;
  icon?: ComponentType;
};

/**
 * The user's selected home view, persisted to localStorage. Kept here (per
 * browser) rather than in backend user config because the set of available
 * views is itself per-browser: plugin sources live in localStorage
 * (`pluginSourcesAtom`), so a backend-synced selection would routinely point at
 * a plugin not installed on another device. `getOnInit: true` mirrors the
 * plugin-source atoms so the very first read returns the persisted value.
 */
export const selectedHomeViewAtom = atomWithStorage<string>(
  "sculptor-selected-home-view",
  BUILTIN_HOME_VIEW_ID,
  undefined,
  { getOnInit: true },
);

/** Options shown in the switcher: the built-in view first, then plugin views. */
export const homeViewOptionsAtom = atom<ReadonlyArray<HomeViewOption>>((get) => {
  const pluginViews = get(pluginHomeViewsAtom);
  return [
    { id: BUILTIN_HOME_VIEW_ID, title: BUILTIN_HOME_VIEW_TITLE },
    ...pluginViews.map((view) => ({ id: view.id, title: view.title, icon: view.icon })),
  ];
});

/**
 * Resolves the selection against what is actually available, falling back to the
 * built-in view when the stored id is gone (e.g. its plugin was unloaded). Pure
 * so the fallback rule is unit-testable without Jotai or the plugin registry.
 */
export const resolveEffectiveHomeViewId = (selectedId: string, availableIds: ReadonlyArray<string>): string =>
  availableIds.includes(selectedId) ? selectedId : BUILTIN_HOME_VIEW_ID;

/** The home view actually rendered, after applying the fallback rule. */
export const effectiveHomeViewIdAtom = atom<string>((get) => {
  const selected = get(selectedHomeViewAtom);
  const options = get(homeViewOptionsAtom);
  return resolveEffectiveHomeViewId(
    selected,
    options.map((option) => option.id),
  );
});
