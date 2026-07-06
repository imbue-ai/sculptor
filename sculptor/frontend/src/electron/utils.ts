// NOTE: you cannot import electron things here because this file is imported both in electron flavor JS and in browser flavor JS.

/**
 * Check if the app is running in Electron environment
 * This checks for the presence of the sculptor API exposed via contextBridge
 */
export const isElectron = (): boolean => {
  return typeof window !== "undefined" && window.sculptor !== undefined;
};

/**
 * Open a native directory selection dialog
 * @returns The selected directory path or null if cancelled
 * @throws Error if not in Electron environment
 */
export const selectProjectDirectory = async (): Promise<string | null> => {
  if (isElectron() && window.sculptor?.selectProjectDirectory) {
    return await window.sculptor.selectProjectDirectory();
  }
  throw new Error("selectProjectDirectory is only available in Electron environment");
};

// Titlebar constants. The titlebar HEIGHT is the --titlebar-height CSS token
// (styles/tokens.css); only the left-padding math lives in TS because it
// branches on the platform.
const SIDEBAR_CLOSED_LEFT_PADDING = 80;
const SIDEBAR_OPEN_LEFT_PADDING = 20;
// On non-macOS platforms there are no left-side traffic-light buttons, so the
// titlebar only needs a small uniform gutter.
const NON_MAC_LEFT_PADDING = 12;
// On macOS the traffic-light buttons are drawn by the OS at a fixed device-pixel
// size and position, but the rest of the page is zoomed via CSS `zoom` on
// document.body. To keep the reserved gutter width matching the native buttons
// regardless of zoom level, divide our base px values by --app-zoom.
const macZoomPaddingCss = (px: number): string => `calc(${px}px / var(--app-zoom))`;
export const getTitleBarLeftPadding = (isSidebarOpen: boolean): string => {
  // On macOS, the titlebar traffic light buttons are on the left, so we need to add padding
  if (!isMac()) {
    return `${NON_MAC_LEFT_PADDING}px`;
  }
  return macZoomPaddingCss(isSidebarOpen ? SIDEBAR_OPEN_LEFT_PADDING : SIDEBAR_CLOSED_LEFT_PADDING);
};

// While the sidebar is collapsed, the top-left gutter holds the traffic lights
// AND the floating show-sidebar toggle (CollapsedSidebarToggle). Any header that
// takes over the window's top edge (the workspace header, a maximized section's
// header) pads by this so its first control doesn't slide under the toggle:
// the traffic-light padding plus one --space-6 (32px) for the toggle button.
export const getCollapsedSidebarToggleClearance = (): string =>
  `calc(${getTitleBarLeftPadding(false)} + var(--space-6))`;

export const isMac = (): boolean => {
  return window.sculptor?.platform === "darwin" || navigator.platform.startsWith("Mac");
};

export const getMetaKey = (): string => {
  return isMac() ? "⌘" : "Ctrl";
};

export const isModifierPressed = (e: KeyboardEvent | React.KeyboardEvent): boolean => {
  return isMac() ? e.metaKey : e.ctrlKey;
};
