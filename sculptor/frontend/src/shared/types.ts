type BaseBackendStatusPayload = { message: string };

export type BackendStatusPayloads = {
  loading: BaseBackendStatusPayload;
  running: BaseBackendStatusPayload;
  warning: BaseBackendStatusPayload;
  error: BaseBackendStatusPayload & { stack: string };
  exited: BaseBackendStatusPayload & { code: number | null; signal: NodeJS.Signals | null; stderr: string };
  unresponsive: BaseBackendStatusPayload;
  // Renderer-only: recent health checks are failing but haven't crossed the
  // threshold to declare the backend unresponsive (e.g. the network is still
  // waking up right after the OS resumes a suspended app). The Electron main
  // process never emits this status.
  reconnecting: BaseBackendStatusPayload;
  shutting_down: BaseBackendStatusPayload;
};

export type BackendStatus<T extends keyof BackendStatusPayloads = keyof BackendStatusPayloads> = {
  status: T;
  payload: BackendStatusPayloads[T];
};

export type AnyBackendStatus = BackendStatus<keyof BackendStatusPayloads>;

export type UpdateChannel = "STABLE" | "RC";

export type AutoUpdateStatus =
  | { type: "disabled" }
  | { type: "idle"; channel: UpdateChannel; latestChannelVersion?: string }
  | { type: "checking"; channel: UpdateChannel }
  | { type: "available"; channel: UpdateChannel; version: string }
  | { type: "downloading"; channel: UpdateChannel; percent: number }
  | { type: "ready"; channel: UpdateChannel; version: string }
  | { type: "error"; channel: UpdateChannel; message: string };

export type CustomBackendSettings = {
  customBackendCommand: string;
  backendReadinessTimeout: number;
};

// Dev-mode metadata exposed by the Electron main process via the
// GET_DEV_INFO IPC channel. Resolves to null in packaged builds. The
// `iconDataUrl` is the same NativeImage used for the dock icon serialized
// at full resolution — the renderer scales it via CSS.
export type SculptorDevInfo = {
  label: string;
  workspaceId: string | null;
  iconDataUrl: string | null;
};

// Type definitions for Electron IPC exposed to the renderer
export type SculptorElectronAPI = {
  selectProjectDirectory: () => Promise<string | null>;
  platform: string;
  getCurrentBackendStatus: () => Promise<AnyBackendStatus>;
  onBackendStatusChange: (callback: (state: AnyBackendStatus) => void) => void;
  removeBackendStatusListener: () => void;
  getSessionToken: () => Promise<string>;
  getBackendPort: () => Promise<number>;
  // File storage operations.
  // `getFileData` is retained to read legacy desktop attachments (saved to disk
  // as absolute paths before uploads moved to the backend); the matching
  // `saveFile` handler was removed once uploads went through the backend.
  getFileData: (filePath: string) => Promise<string>;
  // Auto-update status (pull initial + push updates)
  getAutoUpdateStatus: () => Promise<AutoUpdateStatus>;
  onAutoUpdateStatus: (callback: (status: AutoUpdateStatus) => void) => (...args: Array<unknown>) => void;
  removeAutoUpdateStatusListener: (wrappedCallback: (...args: Array<unknown>) => void) => void;
  // Auto-update commands (renderer → main)
  installUpdate: () => Promise<boolean>;
  checkForUpdate: () => Promise<void>;
  setUpdateChannel: (channel: UpdateChannel) => Promise<void>;
  // Custom backend settings
  getCustomBackendSettings: () => Promise<CustomBackendSettings>;
  setCustomBackendSettings: (settings: Partial<CustomBackendSettings>) => Promise<void>;
  isCustomCommandMode: () => Promise<boolean>;
  getBackendUrl: () => Promise<string | null>;
  getAppVersion: () => Promise<string>;
  // Screenshot capture for feedback reports
  captureScreenshot: () => Promise<ArrayBuffer>;
  // Browser panel: capture the given webview's viewport to the system clipboard.
  captureBrowserPanelToClipboard: (webContentsId: number) => Promise<void>;
  // Browser panel: subscribe to popup-redirect events fired when a webview
  // tries to open a popup (target="_blank" / window.open). The renderer
  // navigates the matching panel's webview instead of spawning a new window.
  onBrowserPanelOpenInPanel: (
    callback: (payload: { webContentsId: number; url: string }) => void,
  ) => (...args: Array<unknown>) => void;
  removeBrowserPanelOpenInPanelListener: (wrappedCallback: (...args: Array<unknown>) => void) => void;
  // Dev-mode metadata: resolves to null in packaged builds.
  getDevInfo: () => Promise<SculptorDevInfo | null>;
  // Zoom commands forwarded from the main process (View menu / accelerators
  // / SCULPTOR_ZOOM_FACTOR). The renderer is the source of truth for the
  // zoom level — it persists the level and applies setZoomFactor itself so
  // the CSS variable update and the Chromium repaint stay in sync.
  onZoomCommand: (callback: (command: ZoomCommand) => void) => (...args: Array<unknown>) => void;
  removeZoomCommandListener: (wrappedCallback: (...args: Array<unknown>) => void) => void;
  setZoomFactor: (factor: number) => void;
  // TEST-ONLY: runs JS inside a Browser panel webview's guest page via its
  // webContentsId. Undefined outside of pytest runs.
  __testBrowserWebviewExecute?: (webContentsId: number, code: string) => Promise<unknown>;
  // TEST-ONLY: reads the system clipboard's PNG image bytes. Undefined outside of pytest runs.
  __testReadClipboardPng?: () => Promise<ArrayBuffer | null>;
};

export type ZoomCommand = { kind: "in" } | { kind: "out" } | { kind: "reset" } | { kind: "setFactor"; factor: number };
