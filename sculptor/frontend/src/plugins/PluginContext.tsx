import { createContext, useContext } from "react";

/**
 * Identifies which plugin a component belongs to. Provided by the host around
 * both a plugin's panel and its settings component, so SDK hooks like
 * `usePluginSetting` can namespace storage by plugin without the author
 * threading the id through.
 */
type PluginContextValue = {
  pluginId: string;
};

export const PluginContext = createContext<PluginContextValue | null>(null);

export const usePluginContext = (): PluginContextValue => {
  const ctx = useContext(PluginContext);
  if (!ctx) {
    throw new Error(
      "Plugin SDK: usePluginSetting called outside a plugin mount. " +
        "It requires the host's PluginContext provider in the component tree.",
    );
  }
  return ctx;
};
