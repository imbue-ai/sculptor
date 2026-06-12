import { useCallback, useState } from "react";

// react-scan highlights components as they re-render — useful while iterating
// on render performance in the dev server. Unlike react-grab it must install
// its instrumentation BEFORE React renders, so enablement is a localStorage
// flag read at boot (see Main.tsx) rather than a live toggle, and flipping the
// switch reloads the app.
const REACT_SCAN_STORAGE_KEY = "sculptor-react-scan";

const isReactScanEnabled = (): boolean => {
  try {
    return localStorage.getItem(REACT_SCAN_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
};

/** Load and start react-scan when dev-enabled. Called from the entry point
 * before `createRoot`; the statically-false DEV branch keeps react-scan out
 * of production bundles entirely. */
export const initializeReactScanIfEnabled = async (): Promise<void> => {
  if (!import.meta.env.DEV || !isReactScanEnabled()) return;
  try {
    const { scan } = await import("react-scan");
    scan({ enabled: true });
  } catch (error) {
    console.error("Failed to load react-scan:", error);
  }
};

type UseReactScanResult = {
  isEnabled: boolean;
  handleCheckedChange: (enabled: boolean) => void;
};

/** Dev-panel toggle state for react-scan. Changing it reloads the window so
 * the boot-time instrumentation can (un)install — the state snapshot taken at
 * mount is therefore never updated in place.
 */
export const useReactScan = (): UseReactScanResult => {
  // eslint-disable-next-line react/hook-use-state -- no setter: the flag only changes via reload
  const [isEnabled] = useState<boolean>(isReactScanEnabled);

  const handleCheckedChange = useCallback((enabled: boolean): void => {
    try {
      localStorage.setItem(REACT_SCAN_STORAGE_KEY, enabled ? "1" : "0");
    } catch {
      return;
    }
    window.location.reload();
  }, []);

  return { isEnabled, handleCheckedChange };
};
