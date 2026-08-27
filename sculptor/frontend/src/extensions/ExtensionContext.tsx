import { createContext, useContext } from "react";

/**
 * Identifies which extension a component belongs to. Provided by the host around
 * both an extension's panel and its settings component, so SDK hooks like
 * `useExtensionSetting` can namespace storage by extension without the author
 * threading the id through.
 */
type ExtensionContextValue = {
  extensionId: string;
};

export const ExtensionContext = createContext<ExtensionContextValue | null>(null);

export const useExtensionContext = (): ExtensionContextValue => {
  const ctx = useContext(ExtensionContext);
  if (!ctx) {
    throw new Error(
      "Extension SDK: useExtensionSetting called outside an extension mount. " +
        "It requires the host's ExtensionContext provider in the component tree.",
    );
  }
  return ctx;
};
