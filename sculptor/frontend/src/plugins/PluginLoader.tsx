import { useAtomValue, useStore } from "jotai";
import { useEffect } from "react";

import { isFrontendPluginsEnabledAtom } from "~/common/state/atoms/userConfig.ts";

import { bootstrapPlugins } from "./pluginManager.tsx";

/**
 * Mounts once at app root and kicks off plugin loading. All the work lives in
 * `pluginManager`, which loads built-in plugins plus every persisted user
 * source. `useStore()` hands the manager the same Jotai store the rest of the
 * app reads from (the app uses a Provider-scoped store, not the default one),
 * so panels and statuses the manager writes are visible to components.
 *
 * Gated behind the experimental frontend-plugins flag. Plugins load once per
 * page load, so flipping the flag takes effect on the next app reload —
 * turning it off mid-session does not unload already-loaded plugins.
 */
export const PluginLoader = (): null => {
  const store = useStore();
  const isEnabled = useAtomValue(isFrontendPluginsEnabledAtom);
  useEffect(() => {
    if (!isEnabled) return;
    bootstrapPlugins(store);
  }, [isEnabled, store]);
  return null;
};
