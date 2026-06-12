import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

export type BrowserViewBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type BrowserViewPlacement = {
  bounds: BrowserViewBounds | null;
  visible: boolean;
};

export type BrowserViewStatus = {
  currentUrl: string;
  canGoBack: boolean;
  canGoForward: boolean;
  isLoading: boolean;
  webContentsId: number | null;
};

export type BrowserViewController = {
  goBack: () => void;
  goForward: () => void;
  reload: () => void;
  navigate: (url: string) => void;
};

const DEFAULT_PLACEMENT: BrowserViewPlacement = { bounds: null, visible: false };

const DEFAULT_STATUS: BrowserViewStatus = {
  currentUrl: "",
  canGoBack: false,
  canGoForward: false,
  isLoading: false,
  webContentsId: null,
};

// Workspaces with a live <webview>. Adding to the set creates the slot;
// removing destroys the webContents. The host renders one slot per entry.
export const browserViewRegistryAtom = atom<ReadonlySet<string>>(new Set<string>());

// Per-workspace placement: bounds in viewport coords, plus a visibility
// flag the host uses to display:none hidden slots without unmounting them.
export const browserViewPlacementAtomFamily = atomFamily((_workspaceId: string) =>
  atom<BrowserViewPlacement>(DEFAULT_PLACEMENT),
);

// Per-workspace status published by the slot, consumed by the toolbar.
export const browserViewStatusAtomFamily = atomFamily((_workspaceId: string) =>
  atom<BrowserViewStatus>(DEFAULT_STATUS),
);

// Identifies which workspace's panel placeholder is currently mounted (if any).
// The slot for this workspace mirrors its webContentsId onto window.__BROWSER_PANEL_TEST__
// so the existing test bridge keeps working without changes to the test harness.
export const focusedBrowserWorkspaceIdAtom = atom<string | null>(null);

// Imperative controllers — refs to webview instance methods. Not Jotai
// state because controllers are imperative and refs grow stale; a module
// singleton keyed by workspaceId is the simplest correct shape.
const controllers = new Map<string, BrowserViewController>();

export const setBrowserViewController = (workspaceId: string, controller: BrowserViewController): void => {
  controllers.set(workspaceId, controller);
};

export const clearBrowserViewController = (workspaceId: string): void => {
  controllers.delete(workspaceId);
};

export const getBrowserViewController = (workspaceId: string): BrowserViewController | undefined => {
  return controllers.get(workspaceId);
};
