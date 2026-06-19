/**
 * Describes what the backend environment supports.
 *
 * Rather than sprinkling `isCustomCommandMode` checks everywhere, components
 * query individual capability flags so the UI adapts to the environment.
 *
 * Capabilities are set once during configureClient() (before React mounts)
 * and never change for the lifetime of the session.
 */
import { atom, getDefaultStore } from "jotai";

import { getBackendCapabilities as fetchBackendCapabilities } from "~/api";

type FileUploadMode = "electron-ipc" | "http";

export type BackendCapabilities = {
  /** Can the backend open files/folders on the host OS? */
  canOpenInOS: boolean;
  /** Can Electron show a native directory picker that the backend can access? */
  canSelectLocalDir: boolean;
  /** How should file uploads/downloads be handled? */
  fileUploadMode: FileUploadMode;
};

const DEFAULT_CLONES_DIR_FALLBACK = "~/.sculptor/repos";

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
 * Absolute path on the backend host where Sculptor will place repos cloned
 * from GitHub when the user doesn't pick a custom target folder.
 * Populated asynchronously by `initBackendCapabilities` from the backend's
 * `/api/v1/config/backend-capabilities` endpoint so the path matches the
 * backend's actual sculptor folder (matters in dev mode, where the folder
 * is repo-local `.dev_sculptor/` rather than `~/.sculptor/`).
 */
export const defaultClonesDirAtom = atom<string>(DEFAULT_CLONES_DIR_FALLBACK);

/**
 * Called once from configureClient(), before React mounts.
 * @param isRemote true when the backend is reached via a custom command (container, SSH, etc.)
 */
export const initBackendCapabilities = (isRemote: boolean): void => {
  capabilities = isRemote ? REMOTE_CAPABILITIES : DEFAULT_CAPABILITIES;
  // Fire-and-forget: the literal fallback covers the first paint; the atom
  // updates once the backend responds. Any error leaves the fallback in
  // place — the clone endpoint will surface a more specific message if the
  // resulting path turns out to be invalid.
  void fetchBackendCapabilities({ meta: { skipWsAck: true } })
    .then(({ data }) => {
      if (data?.defaultClonesDir) {
        getDefaultStore().set(defaultClonesDirAtom, data.defaultClonesDir);
      }
    })
    .catch(() => {
      // Keep the fallback.
    });
};
