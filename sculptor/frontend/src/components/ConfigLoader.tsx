import type { ReactElement, ReactNode } from "react";
import { useEffect } from "react";

import { useUserConfig } from "../common/state/hooks/useUserConfig.ts";

type ConfigLoaderProps = {
  children: ReactNode;
};

/**
 * Loads user configuration on mount so theme, keybindings, and other
 * settings are available before the main app components render.
 */
export const ConfigLoader = ({ children }: ConfigLoaderProps): ReactElement => {
  const { loadConfig } = useUserConfig();

  useEffect(() => {
    // Fire-and-forget on mount. loadConfig also logs failures at its call to the
    // server, but log again here so the fire-and-forget site is not a silent sink
    // and the message records that the app renders on with default settings.
    void loadConfig().catch((error) => {
      console.error("Failed to load user config on mount; continuing with default settings until it loads.", error);
    });
  }, [loadConfig]);

  return <>{children}</>;
};
