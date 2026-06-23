/**
 * Describes what the backend environment supports.
 *
 * Rather than sprinkling `isCustomCommandMode` checks everywhere, components
 * query individual capability flags so the UI adapts to the environment.
 *
 * Capabilities are set once during configureClient() (before React mounts)
 * and never change for the lifetime of the session.
 */

type FileUploadMode = "electron-ipc" | "http";

export type BackendCapabilities = {
  /** Can the backend open files/folders on the host OS? */
  canOpenInOS: boolean;
  /** Can Electron show a native directory picker that the backend can access? */
  canSelectLocalDir: boolean;
  /** How should file uploads/downloads be handled? */
  fileUploadMode: FileUploadMode;
};

const DEFAULT_CAPABILITIES = {
  canOpenInOS: true,
  canSelectLocalDir: true,
  fileUploadMode: "electron-ipc",
} as const satisfies BackendCapabilities;

const REMOTE_CAPABILITIES = {
  canOpenInOS: false,
  canSelectLocalDir: false,
  fileUploadMode: "http",
} as const satisfies BackendCapabilities;

let capabilities: BackendCapabilities = DEFAULT_CAPABILITIES;

/** Read the current capabilities. Safe to call from React components or plain utilities. */
export const getBackendCapabilities = (): BackendCapabilities => capabilities;

/**
 * Called once from configureClient(), before React mounts.
 * @param isRemote true when the backend is reached via a custom command (container, SSH, etc.)
 */
export const initBackendCapabilities = (isRemote: boolean): void => {
  capabilities = isRemote ? REMOTE_CAPABILITIES : DEFAULT_CAPABILITIES;
};
