import { useStore } from "jotai";
import { useEffect } from "react";

import { bootstrapPlugins } from "./pluginManager.tsx";

/**
 * Mounts once at app root and kicks off plugin loading. All the work lives in
 * `pluginManager`, which loads built-in plugins plus every persisted user
 * source. `useStore()` hands the manager the same Jotai store the rest of the
 * app reads from (the app uses a Provider-scoped store, not the default one),
 * so panels and statuses the manager writes are visible to components.
 */
export const PluginLoader = (): null => {
  const store = useStore();
  useEffect(() => {
    bootstrapPlugins(store);
  }, [store]);
  return null;
};
