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
    loadConfig();
  }, [loadConfig]);

  return <>{children}</>;
};
