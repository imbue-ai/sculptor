import { useAtomValue, useStore } from "jotai";
import { type ReactElement, useEffect } from "react";

import { isExtensionsEnabledAtom } from "~/common/state/atoms/userConfig.ts";

import { extensionManager } from "./extensionManager.tsx";

/**
 * Mounts once at app root and kicks off extension loading. All the work lives in
 * `extensionManager`, which loads built-in extensions plus every persisted user
 * source. `useStore()` hands the manager the same Jotai store the rest of the
 * app reads from (the app uses a Provider-scoped store, not the default one),
 * so panels and statuses the manager writes are visible to components.
 *
 * Gated behind the experimental extensions flag. Enabling takes effect
 * immediately — this effect bootstraps extensions as soon as the flag turns on.
 * Disabling is the reload-dependent case: already-loaded extensions are not
 * unloaded mid-session, so turning the flag off only fully takes effect on the
 * next app reload.
 */
export const ExtensionLoader = (): ReactElement | null => {
  const store = useStore();
  const isEnabled = useAtomValue(isExtensionsEnabledAtom);
  useEffect(() => {
    if (!isEnabled) return;
    extensionManager.bootstrap(store);
  }, [isEnabled, store]);
  return null;
};
