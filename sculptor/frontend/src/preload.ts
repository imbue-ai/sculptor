import { contextBridge, ipcRenderer, webFrame } from "electron";

import type { ZoomCommand } from "./electron/constants.ts";
import {
  AUTO_UPDATE_CHECK_CHANNEL_NAME,
  AUTO_UPDATE_INSTALL_CHANNEL_NAME,
  AUTO_UPDATE_SET_CHANNEL_CHANNEL_NAME,
  AUTO_UPDATE_STATUS_CHANNEL_NAME,
  BACKEND_PORT_CHANNEL_NAME,
  BACKEND_STATUS_CHANGE_CHANNEL_NAME,
  BROWSER_PANEL_CAPTURE_TO_CLIPBOARD_CHANNEL_NAME,
  BROWSER_PANEL_OPEN_IN_PANEL_CHANNEL_NAME,
  CAPTURE_SCREENSHOT_CHANNEL_NAME,
  GET_APP_VERSION_CHANNEL_NAME,
  GET_AUTO_UPDATE_STATUS_CHANNEL_NAME,
  GET_CURRENT_BACKEND_STATUS_CHANNEL_NAME,
  GET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME,
  GET_DEV_INFO_CHANNEL_NAME,
  GET_FILE_DATA_CHANNEL_NAME,
  IS_CUSTOM_COMMAND_MODE_CHANNEL_NAME,
  SAVE_FILE_CHANNEL_NAME,
  SELECT_PROJECT_DIRECTORY_CHANNEL_NAME,
  SET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME,
  TEST_BROWSER_WEBVIEW_EXECUTE_CHANNEL_NAME,
  TEST_READ_CLIPBOARD_PNG_CHANNEL_NAME,
  ZOOM_COMMAND_CHANNEL_NAME,
} from "./electron/constants.ts";
import type {
  AnyBackendStatus,
  AutoUpdateStatus,
  CustomBackendSettings,
  SculptorDevInfo,
  UpdateChannel,
} from "./shared/types.ts";

const isInPytest = !!process.env.PYTEST_CURRENT_TEST;

type TestPreloadApi = {
  __testBrowserWebviewExecute: (webContentsId: number, code: string) => Promise<unknown>;
  __testReadClipboardPng: () => Promise<ArrayBuffer | null>;
};

// Preload bindings exposed only when running under pytest. These invoke the
// matching test-only IPC handlers registered by testIpcHandlers.ts and must
// never be merged into the production preload object.
const buildTestPreloadApi = (): TestPreloadApi => ({
  // Executes JavaScript inside a Browser panel webview's guest page.
  __testBrowserWebviewExecute: (webContentsId: number, code: string): Promise<unknown> =>
    ipcRenderer.invoke(TEST_BROWSER_WEBVIEW_EXECUTE_CHANNEL_NAME, webContentsId, code),
  // Reads the system clipboard PNG image bytes for screenshot tests.
  __testReadClipboardPng: (): Promise<ArrayBuffer | null> => ipcRenderer.invoke(TEST_READ_CLIPBOARD_PNG_CHANNEL_NAME),
});

contextBridge.exposeInMainWorld("sculptor", {
  platform: process.platform,
  // Select a project directory using native file dialog
  selectProjectDirectory: () => ipcRenderer.invoke(SELECT_PROJECT_DIRECTORY_CHANNEL_NAME),
  // Get current backend process state
  getCurrentBackendStatus: () => ipcRenderer.invoke(GET_CURRENT_BACKEND_STATUS_CHANNEL_NAME),
  // Register callback for backend process state updates
  onBackendStatusChange: (callback: (state: AnyBackendStatus) => void) =>
    ipcRenderer.on(BACKEND_STATUS_CHANGE_CHANNEL_NAME, (_event, state) => callback(state)),
  // Remove backend state listener
  removeBackendStatusListener: () => ipcRenderer.removeAllListeners(BACKEND_STATUS_CHANGE_CHANNEL_NAME),
  getSessionToken: () => ipcRenderer.invoke("get-session-token"),
  getBackendPort: () => ipcRenderer.invoke(BACKEND_PORT_CHANNEL_NAME),
  // File storage operations
  saveFile: (fileData: ArrayBuffer, filename: string): Promise<string> =>
    ipcRenderer.invoke(SAVE_FILE_CHANNEL_NAME, fileData, filename),
  getFileData: (filePath: string): Promise<string> => ipcRenderer.invoke(GET_FILE_DATA_CHANNEL_NAME, filePath),
  // Auto-update status (pull initial + push updates)
  getAutoUpdateStatus: () => ipcRenderer.invoke(GET_AUTO_UPDATE_STATUS_CHANNEL_NAME),
  onAutoUpdateStatus: (
    callback: (status: AutoUpdateStatus) => void,
  ): ((_event: unknown, status: AutoUpdateStatus) => void) => {
    const wrappedCallback = (_event: unknown, status: AutoUpdateStatus): void => callback(status);
    ipcRenderer.on(AUTO_UPDATE_STATUS_CHANNEL_NAME, wrappedCallback);
    return wrappedCallback;
  },
  removeAutoUpdateStatusListener: (wrappedCallback: (...args: Array<unknown>) => void) =>
    ipcRenderer.off(AUTO_UPDATE_STATUS_CHANNEL_NAME, wrappedCallback),
  // Auto-update commands
  installUpdate: (): Promise<boolean> => ipcRenderer.invoke(AUTO_UPDATE_INSTALL_CHANNEL_NAME),
  checkForUpdate: () => ipcRenderer.invoke(AUTO_UPDATE_CHECK_CHANNEL_NAME),
  setUpdateChannel: (channel: UpdateChannel) => ipcRenderer.invoke(AUTO_UPDATE_SET_CHANNEL_CHANNEL_NAME, channel),
  // Custom backend settings
  getCustomBackendSettings: (): Promise<CustomBackendSettings> =>
    ipcRenderer.invoke(GET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME),
  setCustomBackendSettings: (settings: Partial<CustomBackendSettings>): Promise<void> =>
    ipcRenderer.invoke(SET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME, settings),
  isCustomCommandMode: (): Promise<boolean> => ipcRenderer.invoke(IS_CUSTOM_COMMAND_MODE_CHANNEL_NAME),
  getBackendUrl: (): Promise<string | null> => ipcRenderer.invoke("get-backend-url"),
  getAppVersion: (): Promise<string> => ipcRenderer.invoke(GET_APP_VERSION_CHANNEL_NAME),
  // Screenshot capture for feedback reports
  captureScreenshot: (): Promise<ArrayBuffer> => ipcRenderer.invoke(CAPTURE_SCREENSHOT_CHANNEL_NAME),
  // Browser panel: capture the given webview's viewport to the system clipboard.
  captureBrowserPanelToClipboard: (webContentsId: number): Promise<void> =>
    ipcRenderer.invoke(BROWSER_PANEL_CAPTURE_TO_CLIPBOARD_CHANNEL_NAME, webContentsId),
  // Browser panel: subscribe to popup-redirect events so the renderer can
  // navigate the matching panel's webview when the guest page opens a popup.
  onBrowserPanelOpenInPanel: (
    callback: (payload: { webContentsId: number; url: string }) => void,
  ): ((_event: unknown, payload: { webContentsId: number; url: string }) => void) => {
    const wrappedCallback = (_event: unknown, payload: { webContentsId: number; url: string }): void =>
      callback(payload);
    ipcRenderer.on(BROWSER_PANEL_OPEN_IN_PANEL_CHANNEL_NAME, wrappedCallback);
    return wrappedCallback;
  },
  removeBrowserPanelOpenInPanelListener: (wrappedCallback: (...args: Array<unknown>) => void): void => {
    ipcRenderer.off(BROWSER_PANEL_OPEN_IN_PANEL_CHANNEL_NAME, wrappedCallback);
  },
  // Dev-mode metadata: resolves to null in packaged builds.
  getDevInfo: (): Promise<SculptorDevInfo | null> => ipcRenderer.invoke(GET_DEV_INFO_CHANNEL_NAME),
  // Zoom commands dispatched from the View menu / accelerators (or the
  // SCULPTOR_ZOOM_FACTOR override at startup).
  onZoomCommand: (callback: (command: ZoomCommand) => void): ((...args: Array<unknown>) => void) => {
    const wrappedCallback = (_event: unknown, command: ZoomCommand): void => callback(command);
    ipcRenderer.on(ZOOM_COMMAND_CHANNEL_NAME, wrappedCallback);
    return wrappedCallback as (...args: Array<unknown>) => void;
  },
  removeZoomCommandListener: (wrappedCallback: (...args: Array<unknown>) => void): void => {
    ipcRenderer.off(ZOOM_COMMAND_CHANNEL_NAME, wrappedCallback);
  },
  // Apply a page zoom factor synchronously from the renderer. Pairs with the
  // CSS variable update in useAppZoom so the page repaint and the gutter
  // recompute happen in the same frame (no jitter).
  setZoomFactor: (factor: number): void => {
    webFrame.setZoomFactor(factor);
  },
  ...(isInPytest ? buildTestPreloadApi() : {}),
});
