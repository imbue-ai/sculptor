import { useAtom } from "jotai";
import { useCallback, useEffect } from "react";

import { reactGrabEnabledAtom } from "../../../common/state/atoms/devPanel.ts";

/**
 * Remove all DOM elements injected by react-grab. The library's dispose()
 * method does not fully clean up — it leaves behind a font link, a shadow
 * DOM container, and data attributes. This function removes them manually.
 */
const removeReactGrabElements = (): void => {
  document.querySelectorAll("[data-react-grab]").forEach((el) => el.remove());
  document.getElementById("react-grab-fonts")?.remove();
};

type UseReactGrabResult = {
  isEnabled: boolean;
  handleCheckedChange: (enabled: boolean) => void;
};

/**
 * Manages the react-grab lifecycle. Dynamically imports and initializes
 * react-grab when enabled, and removes it from the DOM when disabled.
 */
export const useReactGrab = (): UseReactGrabResult => {
  const [isEnabled, setIsEnabled] = useAtom(reactGrabEnabledAtom);

  useEffect(() => {
    if (!isEnabled) {
      return;
    }

    let isCancelled = false;

    import("react-grab")
      .then(({ init }) => {
        if (isCancelled) {
          return;
        }
        init();
      })
      .catch((error) => {
        console.error("Failed to load react-grab:", error);
      });

    return (): void => {
      isCancelled = true;
      window.__REACT_GRAB__?.dispose();
      removeReactGrabElements();
    };
  }, [isEnabled]);

  const handleCheckedChange = useCallback(
    (enabled: boolean): void => {
      setIsEnabled(enabled);
    },
    [setIsEnabled],
  );

  return { isEnabled, handleCheckedChange };
};
