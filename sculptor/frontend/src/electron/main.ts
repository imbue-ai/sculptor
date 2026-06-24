import { execSync, spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as readline from "node:readline";
import { pathToFileURL } from "node:url";

import { randomBytes } from "crypto";
import type { MenuItemConstructorOptions } from "electron";
import {
  app,
  BrowserWindow,
  clipboard,
  dialog,
  globalShortcut,
  ipcMain,
  Menu,
  net,
  protocol,
  shell,
  webContents,
} from "electron";
import Store from "electron-store";

import type { AnyBackendStatus, SculptorDevInfo } from "../shared/types";
import { APP_SCHEME, getAppRendererUrl, resolveRequestToFilePath, shouldFallbackToIndex } from "./appProtocol";
import { initAutoUpdater } from "./autoUpdater";
import { captureNonEmptyPage } from "./captureNonEmptyPage";
import type { ZoomCommand } from "./constants";
import {
  BACKEND_PORT_CHANNEL_NAME,
  BACKEND_STATUS_CHANGE_CHANNEL_NAME,
  BROWSER_PANEL_CAPTURE_TO_CLIPBOARD_CHANNEL_NAME,
  BROWSER_PANEL_OPEN_IN_PANEL_CHANNEL_NAME,
  CAPTURE_SCREENSHOT_CHANNEL_NAME,
  GET_APP_VERSION_CHANNEL_NAME,
  GET_AUTO_UPDATE_STATUS_CHANNEL_NAME,
  GET_BACKEND_URL_CHANNEL_NAME,
  GET_CURRENT_BACKEND_STATUS_CHANNEL_NAME,
  GET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME,
  GET_DEV_INFO_CHANNEL_NAME,
  GET_FILE_DATA_CHANNEL_NAME,
  GET_SESSION_TOKEN_CHANNEL_NAME,
  IS_CUSTOM_COMMAND_MODE_CHANNEL_NAME,
  SELECT_PROJECT_DIRECTORY_CHANNEL_NAME,
  SET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME,
  ZOOM_COMMAND_CHANNEL_NAME,
} from "./constants";
import { createDevIcon } from "./devIcon";
import { PORT } from "./electronOnlyUtils";
import { migrateLocalStorageToAppScheme, MIGRATION_BLANK_PATH } from "./localStorageMigration";
import { finalizeLogger, getSculptorFolder, logger } from "./logger";
import { registerTestIpcHandlers } from "./testIpcHandlers";
import {
  flushTracingBeforeExit,
  initializeElectronTracing,
  isTracingEnabled,
  parseTraceToArg,
  setBackendUrlForTracing,
  traceMark,
  tracingTeardownGracePeriodMs,
} from "./tracing";

const isInPytest = !!process.env.PYTEST_CURRENT_TEST;
/* eslint-disable @typescript-eslint/naming-convention */
const IS_DEVELOPMENT = process.env.NODE_ENV === "development";
const IS_MAC = process.platform === "darwin";
const IS_LINUX = process.platform === "linux";

/* eslint-enable @typescript-eslint/naming-convention */

// Mark the custom app scheme as a standard, secure, fetch-capable origin. This
// must run before the app's "ready" event, so it lives at module top level.
// The handler that actually serves files is registered after the app is ready
// (see registerAppProtocolHandler). In a plain `npm run dev` the renderer
// loads over http from the Vite dev server and this scheme goes unused; the
// integration tests opt in via SCULPTOR_USE_APP_SCHEME=1 (see below).
protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true },
  },
]);

// In production the renderer always loads from the custom sculptor://app
// origin. In development it normally loads straight from the Vite dev server
// over http (HMR, fast iteration), but integration tests set
// SCULPTOR_USE_APP_SCHEME=1 to exercise the real app-scheme origin without a
// packaged build: the handler then proxies every request to the Vite dev
// server (injected here as its origin), so Vite still transforms and serves
// the renderer while each request rides sculptor://app.
const APP_SCHEME_DEV_SERVER_ORIGIN =
  IS_DEVELOPMENT && process.env.SCULPTOR_USE_APP_SCHEME === "1"
    ? `http://127.0.0.1:${process.env.SCULPTOR_FRONTEND_PORT || "5173"}`
    : null;

/** Whether the renderer is loaded from sculptor://app (vs. the dev server URL). */
const shouldUseAppScheme = !IS_DEVELOPMENT || APP_SCHEME_DEV_SERVER_ORIGIN !== null;

// When running from source, SCULPTOR_ICON_LABEL controls the large text at the
// top of the dev icon (e.g. "src", "pytest") and SCULPTOR_FRONTEND_PORT is
// shown at the bottom.  The app name in the macOS menu bar/dock is handled
// separately by patching Info.plist in the justfile.  Ignored in packaged builds.
const ICON_LABEL = app.isPackaged ? undefined : process.env.SCULPTOR_ICON_LABEL;
const ICON_PORT = app.isPackaged ? undefined : process.env.SCULPTOR_FRONTEND_PORT;

// Cache the dev icon so the heavy PNG decode + recolor only happens once.
// Both createWindow (dock icon) and the GET_DEV_INFO IPC handler (in-app
// indicator) read from this single source — guaranteeing they match pixel-
// for-pixel and never drift. `undefined` = uninitialized; `null` = packaged
// build or generation failed.
let devIconCache: Electron.NativeImage | null | undefined;
const getDevIcon = (): Electron.NativeImage | null => {
  if (devIconCache === undefined) {
    devIconCache = ICON_LABEL !== undefined ? createDevIcon({ label: ICON_LABEL, port: ICON_PORT }) : null;
  }
  return devIconCache;
};

const getDevInfo = (): SculptorDevInfo | null => {
  if (ICON_LABEL === undefined) return null;
  return {
    label: ICON_LABEL,
    workspaceId: process.env.SCULPT_WORKSPACE_ID ?? null,
    iconDataUrl: getDevIcon()?.toDataURL() ?? null,
  };
};

// Tracing must be initialized before any window or backend work so its
// startup marks land in the combined trace.
const tracePath = parseTraceToArg(process.argv);
if (tracePath !== null) {
  initializeElectronTracing(tracePath);
  traceMark("electron.boot");
}

// We need to pass these flags to disable the keychain as early as possible.
if (IS_MAC) {
  // For macOS: Use mock keychain to avoid prompts
  // This prevents Chromium from accessing the real keychain
  app.commandLine.appendSwitch("use-mock-keychain");
}

if (IS_LINUX) {
  // For Linux: Use basic (unencrypted) storage to avoid keyring prompts
  app.commandLine.appendSwitch("password-store", "basic");
}

let pythonBackgroundProcess: ReturnType<typeof spawn> | null = null;
let window: BrowserWindow | null = null;
let currentBackendStatus: AnyBackendStatus = { status: "loading", payload: { message: "Initializing..." } };
let stderrBuffer = "";
let isQuitting = false;
// True only during the one-time startup localStorage migration, which opens and
// destroys a transient window before the main window exists. Destroying it would
// otherwise fire window-all-closed and quit the app mid-startup (see the handler).
let isMigrating = false;
let autoUpdaterManager: ReturnType<typeof initAutoUpdater> = null;
let isInCustomCommandMode = false;
let customCommandBackendUrl: string | null = null;
// Resolved once customCommandBackendUrl is set (or immediately if not in custom command mode).
let resolveBackendUrl: ((url: string | null) => void) | null = null;
const backendUrlReady: Promise<string | null> = new Promise((resolve) => {
  resolveBackendUrl = resolve;
});
let restartCount = 0;
const MAX_RESTARTS = 3;
const RESTART_BASE_DELAY_MS = 2000;

const MAX_STDERR_BUFFER_SIZE = 10 * 1024 * 1024; // 10 MB
const MAX_BYTE_PER_CHARACTER = 4; // at worst characters are 4 bytes in JS
const MAX_CHARACTERS_IN_BUFFER = Math.ceil(MAX_STDERR_BUFFER_SIZE / MAX_BYTE_PER_CHARACTER);

// Constants for timeouts and intervals
const PRODUCTION_BACKEND_READINESS_TIMEOUT_MS = 20000; // 20 secs
const DEVELOPMENT_BACKEND_READINESS_TIMEOUT_MS = 10000; // 10 secs
const TESTING_BACKEND_READINESS_TIMEOUT_MS = 60000; // 60 secs
const RETRY_INTERVAL_MS = 200; // 200ms between retries for fast detection
const INITIAL_WAIT_MS = 100; // 100ms initial wait before first check

// How long to wait for the backend to drain and exit on shutdown before
// escalating to SIGKILL. The default-mode backend gets a longer budget because
// its --trace-to teardown can take many seconds to flush viztracer.
const CUSTOM_COMMAND_SHUTDOWN_GRACE_PERIOD_MS = 15000;
const DEFAULT_BACKEND_SHUTDOWN_GRACE_PERIOD_MS = 32000;

// Window configuration constants
const WINDOW_WIDTH = 1200;
const WINDOW_HEIGHT = 800;
const MIN_WINDOW_WIDTH = 600;
const MIN_WINDOW_HEIGHT = 600;

const SCULPTOR_ARG_PREFIX = "--sculptor=";

// Generate a session token for CSRF-like protection
// Allow using an external session token via environment variable (for remote headless sculptor connections)
// Falls back to generating a random token if not provided
const SESSION_TOKEN = process.env.SCULPTOR_SESSION_TOKEN || randomBytes(32).toString("hex");

// Log whether we're using an external or generated token (without revealing the actual token)
if (process.env.SCULPTOR_SESSION_TOKEN) {
  logger.info("[main] Using session token from SCULPTOR_SESSION_TOKEN environment variable");
} else {
  logger.info("[main] Generated new session token for this session");
}

// Important: Keep the following two block executed as early as possible.
const userDataOverride = process.env.SCULPTOR_USER_DATA_DIR;
if (userDataOverride) {
  app.setPath("userData", userDataOverride);
  // Also redirect the cache directory so that libraries like electron-updater
  // (which stores downloads in app.getPath("cache")) don't leak state between
  // test instances or across CI runs on persistent runners.
  app.setPath("cache", path.join(userDataOverride, "cache"));
} else if (!app.isPackaged || app.getVersion().includes("-dev.")) {
  app.setPath("userData", path.join(getSculptorFolder(), "internal", "electron"));
}

if (app.isPackaged && !isInPytest) {
  // Prevent multiple instances for the packaged version of the app.
  // We don't enforce that for unpackaged apps since it can still be useful for testing.
  // Skip in pytest mode to avoid blocking app.whenReady() on CI runners.
  // For more documentation, look for 74643a8d-5e1d-4b5d-9b36-62cafce687ca.
  if (!app.requestSingleInstanceLock()) {
    logger.warn("[main] Another instance of Sculptor is already running, quitting.");
    process.exit(1);
  }

  const focusWindow = (): void => {
    if (!isQuitting && window) {
      window.focus();
    }
  };
  app.on("second-instance", focusWindow);
  app.on("activate", focusWindow);
}

const store = new Store({
  defaults: {
    windowBounds: {
      width: WINDOW_WIDTH,
      height: WINDOW_HEIGHT,
    },
    updateChannel: "STABLE",
    customBackendCommand: "",
    backendReadinessTimeout: 60,
  },
});

const sleep = (ms: number): Promise<void> => {
  return new Promise((resolve) => setTimeout(resolve, ms));
};

const sendBackendState = (state: AnyBackendStatus): void => {
  currentBackendStatus = state;
  if (window?.webContents) {
    window.webContents.send(BACKEND_STATUS_CHANGE_CHANNEL_NAME, state);
  }
};

// Page zoom commands. The renderer is the source of truth: it owns the level,
// calls webFrame.setZoomFactor (so canvas/terminal content and the layout
// viewport are handled by Chromium), and updates the --app-zoom CSS variable
// the title-bar gutter divides by — all in one synchronous task so the page
// and the gutter repaint together (no jitter).
const sendZoomCommand = (command: ZoomCommand): void => {
  window?.webContents.send(ZOOM_COMMAND_CHANNEL_NAME, command);
};

const URL_PATTERN = /https?:\/\/[^\s]+:\d+/;

const parseUrlFromStdout = (stdout: NodeJS.ReadableStream, timeoutMs: number): Promise<string> => {
  return new Promise((resolve, reject) => {
    const collectedLines: Array<string> = [];
    const rl = readline.createInterface({ input: stdout });

    const timer = setTimeout(() => {
      reject(
        new Error(`No backend URL found in stdout within ${timeoutMs / 1000}s. Output:\n${collectedLines.join("\n")}`),
      );
      rl.close();
    }, timeoutMs);

    rl.on("line", (line) => {
      const match = line.match(URL_PATTERN);

      if (match) {
        clearTimeout(timer);
        resolve(match[0]);
        rl.close();
      } else {
        collectedLines.push(line);
        logger.info(`[custom-command stdout] ${line}`);
      }
    });

    rl.on("close", () => {
      clearTimeout(timer);
      reject(new Error(`stdout closed before a backend URL was found. Output:\n${collectedLines.join("\n")}`));
    });
  });
};

// Wait for backend to be ready by polling the health endpoint
const waitForBackend = async (
  urlOrPort: number | string,
  host = "127.0.0.1",
  timeoutOverrideMs?: number,
): Promise<boolean> => {
  const baseUrl = typeof urlOrPort === "string" ? urlOrPort : `http://${host}:${urlOrPort}`;
  const start = performance.now();
  const timeoutMs =
    timeoutOverrideMs ??
    (isInPytest
      ? TESTING_BACKEND_READINESS_TIMEOUT_MS
      : IS_DEVELOPMENT
        ? DEVELOPMENT_BACKEND_READINESS_TIMEOUT_MS
        : PRODUCTION_BACKEND_READINESS_TIMEOUT_MS);

  logger.info(`[main] waiting for backend at ${baseUrl}/api/v1/health`);

  // Give the backend process some time to start before first check
  await sleep(INITIAL_WAIT_MS);

  while (performance.now() - start < timeoutMs) {
    if (isQuitting) {
      return false;
    }

    try {
      // TODO: verify that all backend services are ready, not just the HTTP server.
      const response = await fetch(`${baseUrl}/api/v1/health`);

      if (response.ok) {
        const healthData = await response.text();
        logger.info(`[main] backend ready, health data: ${healthData}`);
        return true;
      }
    } catch {
      // Backend not ready yet, this is expected during startup
      const elapsed = Math.round((performance.now() - start) / 1000);
      logger.info(`[main] backend not ready yet (${elapsed}s elapsed), retrying...`);
    }

    await sleep(RETRY_INTERVAL_MS);
  }

  logger.warn(`Backend failed to start within ${timeoutMs / 1000} seconds`);
  return false;
};

const setupProcessHandlers = (proc: ReturnType<typeof spawn>): void => {
  proc.stderr?.on("data", (data) => {
    stderrBuffer += data.toString();

    const excessLength = stderrBuffer.length - MAX_CHARACTERS_IN_BUFFER;

    if (excessLength > 0) {
      stderrBuffer = stderrBuffer.slice(excessLength, stderrBuffer.length);
    }

    try {
      process.stderr.write(data);
    } catch {
      // Swallow — can fail if the app has crashed
    }
  });

  proc.on("error", (err: Error) => {
    logger.error("[main] backend spawn error:", err);

    if (!isQuitting) {
      sendBackendState({
        status: "error",
        payload: {
          message: err.message,
          stack: err.stack,
        },
      });
    }
  });

  proc.on("exit", (code, signal) => {
    if (isQuitting) {
      return;
    }

    if (isInCustomCommandMode && restartCount < MAX_RESTARTS) {
      logger.warn(
        `[main] custom command exited code=${code} signal=${signal}, stderr: ${stderrBuffer.trim().slice(-500) || "(empty)"}`,
      );
      restartCustomCommand().catch((err) => {
        logger.error("[main] restart failed:", err);
        sendBackendState({
          status: "error",
          payload: {
            message: `Backend restart failed: ${(err as Error).message}`,
            stack: (err as Error).stack,
          },
        });
      });

      return;
    }

    if (isInCustomCommandMode && restartCount >= MAX_RESTARTS) {
      logger.error(
        `[main] custom command failed after ${MAX_RESTARTS} attempts, last exit code=${code} signal=${signal}, stderr: ${stderrBuffer.trim().slice(-500) || "(empty)"}`,
      );
      sendBackendState({
        status: "error",
        payload: {
          message: `Backend could not be started after ${MAX_RESTARTS} attempts`,
          stack: stderrBuffer.trim().slice(-500),
        },
      });

      return;
    }

    logger.warn(`[main] backend exited code=${code} signal=${signal}`);
    const exitMessage = signal ? `Backend killed with signal ${signal}` : `Backend exited with code ${code}`;
    sendBackendState({
      status: "exited",
      payload: {
        code,
        signal,
        stderr: stderrBuffer.trim(),
        message: exitMessage,
      },
    });
  });
};

const spawnCustomCommand = (customCommand: string): void => {
  const shellPath = getShellPath();

  logger.info(`[main] spawning custom backend command: ${customCommand}`);

  const updateChannel = store.get("updateChannel", "STABLE") as string;
  const sculptorChannel = updateChannel === "STABLE" ? "slim" : "slim-rc";

  pythonBackgroundProcess = spawn("sh", ["-c", customCommand], {
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      SESSION_TOKEN: SESSION_TOKEN,
      SCULPTOR_VERSION: app.getVersion(),
      SCULPTOR_CHANNEL: sculptorChannel,
      PATH: shellPath,
    },
    detached: true,
  });

  setupProcessHandlers(pythonBackgroundProcess);
};

const restartCustomCommand = async (): Promise<void> => {
  restartCount++;
  const delay = restartCount * RESTART_BASE_DELAY_MS;

  logger.info(`[main] restarting custom command (attempt ${restartCount}/${MAX_RESTARTS}), delay ${delay}ms`);
  sendBackendState({
    status: "loading",
    payload: { message: `Backend exited unexpectedly. Restarting (attempt ${restartCount}/${MAX_RESTARTS})...` },
  });

  await sleep(delay);

  if (isQuitting) {
    return;
  }

  const customCommand = process.env.SCULPTOR_CUSTOM_BACKEND_CMD || (store.get("customBackendCommand", "") as string);

  if (!customCommand) {
    sendBackendState({
      status: "error",
      payload: { message: "Custom backend command is empty, cannot restart", stack: "" },
    });

    return;
  }

  stderrBuffer = "";
  spawnCustomCommand(customCommand);

  const readinessTimeoutSec = store.get("backendReadinessTimeout", 60) as number;
  const readinessTimeoutMs = readinessTimeoutSec * 1000;

  try {
    customCommandBackendUrl = await parseUrlFromStdout(pythonBackgroundProcess!.stdout!, readinessTimeoutMs);
    resolveBackendUrl?.(customCommandBackendUrl);
    logger.info(`[main] parsed backend URL from restarted command: ${customCommandBackendUrl}`);

    pythonBackgroundProcess!.stdout?.on("data", (data) => {
      try {
        process.stdout.write(data);
      } catch {
        // Swallow
      }
    });
  } catch (err) {
    logger.error("[main] failed to parse URL from restarted command:", err);
    sendBackendState({
      status: "error",
      payload: {
        message: `Custom command did not output a backend URL: ${(err as Error).message}`,
        stack: (err as Error).stack,
      },
    });

    return;
  }

  const isRunning = await waitForBackend(customCommandBackendUrl, undefined, readinessTimeoutMs);

  if (isRunning && !isQuitting) {
    restartCount = 0;
    sendBackendState({ status: "running", payload: { message: "Backend is running." } });
  }
};

// Where to launch the sidecar from in DEV vs PROD
const getBackendCommand = async (): Promise<{ cmd: string; args: Array<string> }> => {
  // Get command line arguments, filtering out Electron-specific ones
  // In packaged apps, arguments might come from different sources
  logger.info("[main] Raw process.argv:", process.argv);
  logger.info("[main] app.isPackaged:", app.isPackaged);

  // Skip the binary path, plus the project directory in dev mode
  // (https://github.com/electron/electron/issues/4690).
  const argv = process.argv.slice(app.isPackaged ? 1 : 2);
  const userArgs = argv.flatMap((arg) =>
    arg.startsWith(SCULPTOR_ARG_PREFIX) ? [arg.slice(SCULPTOR_ARG_PREFIX.length)] : [],
  );

  // If the user passed --trace-to directly to Electron (rather than via
  // --sculptor=--trace-to), forward it to the backend too so both sides write
  // to the same combined trace file.
  if (isTracingEnabled() && tracePath !== null && !userArgs.some((a) => a.startsWith("--trace-to="))) {
    userArgs.push(`--trace-to=${tracePath}`);
  }

  logger.info("[main] Filtered user args:", userArgs);

  // Base arguments for sculptor_main
  const baseArgs = ["--port", String(await PORT), "--no-open-browser", "--packaged-entrypoint"];

  const exe = "sculptor_backend/sculptor_backend";
  const bin = path.join(resourcesPath(), exe);
  // Pass through all user arguments to sculptor_main
  return { cmd: bin, args: [...baseArgs, ...userArgs] };
};

const resourcesPath = (): string => {
  // Packaged apps have resource files defined in extraResource in forge.config.ts available.
  // In development, Electron Forge doesn't copy those files,
  // but we can find them relative to SCULPTOR_FRONTEND_DIR (set in electron:start script in package.json).
  return app.isPackaged ? process.resourcesPath : path.join(process.env.SCULPTOR_FRONTEND_DIR!, "../dist");
};

/**
 * Get the PATH environment variable from the user's login shell.
 *
 * When Electron apps are launched from Finder/Launchpad (not from terminal), they don't inherit
 * the user's shell PATH. This means tools installed via Homebrew, nvm, etc. won't be found.
 *
 * A login shell (`-l`) only sources ~/.zprofile and ~/.zshenv (for zsh) or ~/.bash_profile (for
 * bash). Many users configure their PATH in ~/.zshrc or ~/.bashrc, which are only sourced in
 * interactive shells. Rather than using `-i` (which risks triggering interactive prompts like
 * oh-my-zsh updates), we explicitly source the rc file within a login shell.
 *
 * Output is wrapped in unique markers to avoid contamination from shell startup messages.
 */
const getShellPath = (): string => {
  const userShell = process.env.SHELL || "/bin/zsh";
  const shellName = path.basename(userShell);
  const marker = `__SCULPTOR_PATH_${Date.now()}__`;

  const rcFile = shellName === "zsh" ? "~/.zshrc" : shellName === "bash" ? "~/.bashrc" : null;
  const sourceRc = rcFile ? `[ -f ${rcFile} ] && source ${rcFile};` : "";

  try {
    const output = execSync(`${userShell} -l -c '${sourceRc} echo ${marker}; echo "$PATH"; echo ${marker}'`, {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const lines = output.split("\n");
    const startIdx = lines.indexOf(marker);
    const endIdx = lines.lastIndexOf(marker);
    if (startIdx !== -1 && endIdx !== -1 && startIdx < endIdx) {
      return lines
        .slice(startIdx + 1, endIdx)
        .join("")
        .trim();
    }

    logger.warn("[main] getShellPath: could not find markers in shell output, using raw output");
    return output.trim();
  } catch (e) {
    logger.warn("[main] getShellPath: failed to get PATH from shell, using process.env.PATH:", e);
    return process.env.PATH || "";
  }
};

const urlStartsWith = (url1: string, url2: string): boolean => {
  return url1 === url2 || url1.startsWith(url2.endsWith("/") ? url2 : url2 + "/");
};

const toggleDevTools = (window: BrowserWindow): void => {
  if (window.webContents.isDevToolsOpened()) {
    window.webContents.closeDevTools();
  } else {
    window.webContents.openDevTools({ mode: "detach" });
  }
};

const createApplicationMenu = (): void => {
  const isMac = process.platform === "darwin";

  const template: Array<MenuItemConstructorOptions> = [
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: "hide" as const },
              { role: "hideOthers" as const },
              { role: "unhide" as const },
              { type: "separator" as const },
              {
                label: "Quit Sculptor",
                accelerator: "CommandOrControl+Q",
                click: (): void => {
                  // Route through window.close() so the confirmation dialog shows.
                  // Falls back to app.quit() if no window is open.
                  if (window) {
                    window.close();
                  } else {
                    app.quit();
                  }
                },
              },
            ],
          },
        ]
      : [
          {
            label: "File",
            submenu: [
              {
                label: "Quit",
                accelerator: "CommandOrControl+Q",
                click: (): void => {
                  if (window) {
                    window.close();
                  } else {
                    app.quit();
                  }
                },
              },
            ],
          },
        ]),
    {
      label: "Edit",
      submenu: [
        { role: "undo" as const },
        { role: "redo" as const },
        { type: "separator" as const },
        { role: "cut" as const },
        { role: "copy" as const },
        { role: "paste" as const },
        {
          role: "pasteAndMatchStyle" as const,
          accelerator: "CommandOrControl+Shift+V",
        },
        { role: "selectAll" as const },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" as const },
        { role: "forceReload" as const },
        { role: "toggleDevTools" as const },
        { type: "separator" as const },
        {
          label: "Actual Size",
          accelerator: "CommandOrControl+0",
          click: () => sendZoomCommand({ kind: "reset" }),
        },
        {
          // Cover both Cmd+= (the unshifted key) and Cmd++ so users get the
          // shortcut whether or not they hold Shift. We register the two
          // accelerators on separate (visible/hidden) menu items because a
          // single MenuItem only takes one accelerator.
          label: "Zoom In",
          accelerator: "CommandOrControl+Plus",
          click: () => sendZoomCommand({ kind: "in" }),
        },
        {
          label: "Zoom In",
          accelerator: "CommandOrControl+=",
          click: () => sendZoomCommand({ kind: "in" }),
          visible: false,
        },
        {
          label: "Zoom Out",
          accelerator: "CommandOrControl+-",
          click: () => sendZoomCommand({ kind: "out" }),
        },
        { type: "separator" as const },
        { role: "togglefullscreen" as const },
      ],
    },
    {
      label: "Window",
      submenu: [
        { role: "minimize" as const },
        { role: "zoom" as const },
        ...(isMac ? [{ role: "close" as const }] : []),
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
};

const createWindow = async (): Promise<void> => {
  const savedBounds = store.get("windowBounds", {
    width: WINDOW_WIDTH,
    height: WINDOW_HEIGHT,
  }) as { width: number; height: number; x?: number; y?: number };

  if (isInPytest) {
    savedBounds.width = 1600;
    savedBounds.height = 1000;
  }

  // When running from source, generate an inverted + hue-shifted icon with
  // text overlays for visual distinction between instances. The same
  // NativeImage drives the dock icon and (via `getDevInfo` IPC) the in-app
  // DevModeIndicator, so the two are guaranteed to match pixel-for-pixel.
  const devIconImage = getDevIcon();
  if (devIconImage && IS_MAC) {
    app.dock?.setIcon(devIconImage);
  }

  window = new BrowserWindow({
    width: savedBounds.width,
    height: savedBounds.height,
    x: savedBounds.x,
    y: savedBounds.y,
    minWidth: MIN_WINDOW_WIDTH,
    minHeight: MIN_WINDOW_HEIGHT,
    icon: devIconImage || path.join(__dirname, "..", "..", "assets", "icons", "icon.png"),
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    skipTaskbar: false,
    show: !isInPytest, // Don't auto-show during tests; we'll use showInactive() instead
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: true,
      webviewTag: true,
    },
  });

  // Show window without stealing focus during tests
  if (isInPytest) {
    window.showInactive();
  }

  // SCULPTOR_ZOOM_FACTOR (used by integration tests) overrides the user's
  // persisted zoom for this session. Forward it to the renderer once the page
  // has loaded; the renderer applies it without touching the stored level so
  // the override doesn't bleed into normal sessions.
  const envZoomFactor = process.env.SCULPTOR_ZOOM_FACTOR;
  if (envZoomFactor) {
    window.webContents.on("did-finish-load", () => {
      const factor = Number(envZoomFactor);
      sendZoomCommand({ kind: "setFactor", factor });
      logger.info(`[main] set zoom factor to ${factor} from SCULPTOR_ZOOM_FACTOR`);
    });
  }

  // In production (and tests that opt in via SCULPTOR_USE_APP_SCHEME) the
  // renderer loads from the custom, secure sculptor://app origin served by the
  // app protocol instead of file://. A real origin makes absolute paths, fetch,
  // dynamic import, and CSP behave like a normal web page; the backend CORS
  // allowlist accepts it (see sculptor/web/app.py). In plain development it
  // loads straight from the Vite dev server over http.
  //
  // We construct the dev server URL from SCULPTOR_FRONTEND_PORT (populated at
  // runtime) rather than MAIN_WINDOW_VITE_DEV_SERVER_URL: that Vite define is
  // substituted at compile time, so concurrent dev instances (as in integration
  // tests) would race to write it and could open the wrong URL.
  const appUrl = shouldUseAppScheme
    ? getAppRendererUrl()
    : `http://localhost:${process.env.SCULPTOR_FRONTEND_PORT || "5173"}`;

  logger.info("[main] Initial URL:", appUrl);
  await window.loadURL(appUrl);

  // Only show the native context menu on editable fields (inputs, textareas).
  // Non-editable areas are left to the renderer (e.g. Radix ContextMenu).
  window.webContents.on("context-menu", (_event, params) => {
    if (!window) return; // Only to prove to the type checker that window is non-null below
    if (params.isEditable) {
      const menuItems: Array<MenuItemConstructorOptions> = [];

      // Add spelling suggestions when a word is misspelled
      if (params.misspelledWord) {
        for (const suggestion of params.dictionarySuggestions) {
          menuItems.push({
            label: suggestion,
            click: () => window.webContents.replaceMisspelling(suggestion),
          });
        }

        if (params.dictionarySuggestions.length > 0) {
          menuItems.push({ type: "separator" });
        }
        menuItems.push({
          label: "Add to Dictionary",
          click: () => window.webContents.session.addWordToSpellCheckerDictionary(params.misspelledWord),
        });
        menuItems.push({ type: "separator" });
      }

      menuItems.push(
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { type: "separator" },
        { role: "selectAll" },
      );

      Menu.buildFromTemplate(menuItems).popup({ window, x: params.x, y: params.y });
    }
  });

  // This is necessary to prevent the ttyd terminal from blocking window close events.
  window.webContents.on("will-prevent-unload", (e) => {
    e.preventDefault();
  });

  // Don't let the window navigate away from the Sculptor app.
  // This handles links with target="_blank".
  window.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url);
    return { action: "deny" };
  });

  // Browser panel <webview> elements. Keep `target="_blank"` links and
  // `window.open` calls inside the same panel instead of spawning an OS
  // window. Two layers:
  //
  // 1. setWindowOpenHandler on the guest webContents catches window.open()
  //    and form-submit popups; we deny the popup and tell the renderer to
  //    navigate the matching panel.
  // 2. A small script injected on every dom-ready intercepts clicks on
  //    `<a target="_blank">` links before Chromium's popup blocker can
  //    decide they came without user activation. It rewrites them to
  //    navigate the same frame, which keeps the panel pointed at the
  //    expected URL even for synthetic clicks. (`allowpopups` on the
  //    <webview> tag is not enough — verified empirically:
  //    test_browser_panel_navigation_tour fails on the synthetic
  //    `popup-link.click()` without this interceptor.)
  window.webContents.on("did-attach-webview", (_event, attachedContents) => {
    attachedContents.setWindowOpenHandler(({ url }) => {
      window?.webContents.send(BROWSER_PANEL_OPEN_IN_PANEL_CHANNEL_NAME, {
        webContentsId: attachedContents.id,
        url,
      });
      return { action: "deny" };
    });
    const injectTargetBlankInterceptor = (): void => {
      void attachedContents
        .executeJavaScript(
          `
          (() => {
            if (window.__sculptorBrowserPanelHooksInstalled) return;
            window.__sculptorBrowserPanelHooksInstalled = true;
            document.addEventListener("click", (event) => {
              const link = event.target instanceof Element ? event.target.closest("a[target=_blank]") : null;
              if (!link) return;
              const href = link.href;
              if (!href) return;
              event.preventDefault();
              window.location.href = href;
            }, true);
          })();
          `,
        )
        .catch(() => {
          // Swallow: the page may have navigated away before we could inject.
        });
    };
    attachedContents.on("dom-ready", injectTargetBlankInterceptor);
  });

  // This handles other links.
  window.webContents.on("will-navigate", (event, url) => {
    if (!urlStartsWith(url, appUrl)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  const saveWindowBounds = (): void => {
    if (!window) return;
    const bounds = window.getBounds();
    store.set("windowBounds", bounds);
  };

  window.on("resize", saveWindowBounds);
  window.on("move", saveWindowBounds);

  // Register local shortcuts for dev tools (only when window is focused)
  window.webContents.on("before-input-event", (event, input) => {
    if (input.key === "F12" && input.type === "keyDown") {
      toggleDevTools(window!);
    }

    if (process.platform === "darwin" && input.key === "i" && input.meta && input.alt && input.type === "keyDown") {
      toggleDevTools(window!);
    }
  });

  // Intercept window close to show a confirmation dialog.
  // Skip if already quitting (e.g., user already confirmed, or auto-update).
  window.on("close", (e) => {
    if (isQuitting) return;
    if (autoUpdaterManager?.isUpdating) return;

    e.preventDefault();
    logger.info("[main] window close intercepted, showing confirmation dialog");

    dialog
      .showMessageBox(window!, {
        type: "question",
        buttons: ["Quit", "Cancel"],
        defaultId: 0,
        cancelId: 1,
        title: "Quit Sculptor",
        message: "Are you sure you want to quit Sculptor?",
        detail: "Any running agents will be stopped.",
      })
      .then(async ({ response }) => {
        if (response !== 0) return;
        logger.info("[main] user confirmed quit from window close");
        await shutdownBackend("Shutting down...");
        globalShortcut.unregisterAll();
        app.quit();
      });
  });

  window.on("closed", (): void => {
    window = null;
  });
};

/**
 * Serve the built renderer bundle over the custom `sculptor://app` scheme.
 * Maps each request to a file inside the bundle directory (with a path-
 * traversal guard) and streams it back via `net.fetch`, which infers the MIME
 * type from the extension. Extensionless misses fall back to the SPA shell.
 * This file-serving branch is the packaged-build path; under
 * SCULPTOR_USE_APP_SCHEME=1 (integration tests) the handler instead proxies to
 * the Vite dev server. Only a plain `npm run dev` never hits this handler.
 */
const registerAppProtocolHandler = (): void => {
  const bundleDir = path.join(app.getAppPath(), ".vite/build/renderer");
  protocol.handle(APP_SCHEME, async (request) => {
    const { pathname, search } = new URL(request.url);
    // Blank doc for the one-time localStorage origin migration: lets the main
    // process open a page on this origin to write without booting the renderer.
    if (pathname === MIGRATION_BLANK_PATH) {
      return new Response('<!doctype html><meta charset="utf-8"><title>migrating</title>', {
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }

    if (APP_SCHEME_DEV_SERVER_ORIGIN !== null) {
      // Test/dev: proxy to the Vite dev server, preserving path + query so its
      // on-the-fly module transforms and asset requests resolve there. (The
      // app's API/WebSocket traffic goes straight to the backend via absolute
      // URLs, so it never reaches this handler.)
      return net.fetch(`${APP_SCHEME_DEV_SERVER_ORIGIN}${pathname}${search}`);
    }
    const resolved = resolveRequestToFilePath(bundleDir, request.url);
    if (resolved === null) {
      return new Response("Bad request", { status: 400 });
    }
    let target = resolved;
    // TODO(SCU-1517): this serves one fixed bundle at startup, so a sync stat
    // is fine. Once the handler also serves plugins from arbitrary local
    // directories at runtime, switch existsSync (and the read below) to async
    // fs.promises to keep the main process thread non-blocking.
    if (!fs.existsSync(target)) {
      if (shouldFallbackToIndex(target)) {
        target = path.join(bundleDir, "index.html");
      } else {
        return new Response("Not found", { status: 404 });
      }
    }
    return net.fetch(pathToFileURL(target).toString());
  });
};

app.whenReady().then(async () => {
  // Register the app-scheme file handler before any window loads from it.
  registerAppProtocolHandler();

  // One-time: carry renderer localStorage from the legacy file:// origin to
  // sculptor://app before any window loads, so an in-place upgrade keeps the
  // user's layout, theme, tabs, etc. Gated, capped, and never throws.
  if (app.isPackaged && shouldUseAppScheme && !isInPytest) {
    // Suppress the window-all-closed quit while the migration's transient window
    // opens and closes (the main window doesn't exist yet). Cleared once the
    // main window is created, below.
    isMigrating = true;
    await migrateLocalStorageToAppScheme(store);
  }

  traceMark("electron.app_ready");
  createApplicationMenu();

  ipcMain.handle(BACKEND_PORT_CHANNEL_NAME, () => PORT);
  ipcMain.handle(SELECT_PROJECT_DIRECTORY_CHANNEL_NAME, async () => {
    if (!window) {
      return null;
    }
    const result = await dialog.showOpenDialog(window, {
      properties: ["openDirectory"],
      title: "Select Project Directory",
      buttonLabel: "Select",
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle(GET_CURRENT_BACKEND_STATUS_CHANNEL_NAME, () => {
    return currentBackendStatus;
  });

  ipcMain.handle(GET_SESSION_TOKEN_CHANNEL_NAME, () => {
    return SESSION_TOKEN;
  });

  ipcMain.handle(GET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME, () => {
    return {
      customBackendCommand: store.get("customBackendCommand") as string,
      backendReadinessTimeout: store.get("backendReadinessTimeout") as number,
    };
  });

  ipcMain.handle(
    SET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME,
    (_event, settings: { customBackendCommand?: string; backendReadinessTimeout?: number }) => {
      if (settings.customBackendCommand !== undefined) {
        store.set("customBackendCommand", settings.customBackendCommand);
      }

      if (settings.backendReadinessTimeout !== undefined) {
        store.set("backendReadinessTimeout", settings.backendReadinessTimeout);
      }
    },
  );

  ipcMain.handle(IS_CUSTOM_COMMAND_MODE_CHANNEL_NAME, () => isInCustomCommandMode);
  ipcMain.handle(GET_DEV_INFO_CHANNEL_NAME, () => getDevInfo());
  ipcMain.handle(GET_APP_VERSION_CHANNEL_NAME, () => app.getVersion());
  ipcMain.handle(GET_BACKEND_URL_CHANNEL_NAME, () => backendUrlReady);

  ipcMain.handle(CAPTURE_SCREENSHOT_CHANNEL_NAME, async () => {
    if (!window) {
      throw new Error("No window available for screenshot capture");
    }
    const image = await window.webContents.capturePage();
    const png = image.toPNG();
    return png.buffer.slice(png.byteOffset, png.byteOffset + png.byteLength);
  });

  ipcMain.handle(BROWSER_PANEL_CAPTURE_TO_CLIPBOARD_CHANNEL_NAME, async (_event, webContentsId: number) => {
    const contents = webContents.fromId(webContentsId);
    if (!contents) {
      throw new Error(`No webContents with id ${webContentsId}`);
    }
    // Retry until the guest has painted: capturePage() resolves with an empty
    // image until the first frame is composited, and writing that empty image
    // would leave no PNG on the clipboard.
    const image = await captureNonEmptyPage(contents);
    clipboard.writeImage(image);
  });

  if (isInPytest) {
    registerTestIpcHandlers(ipcMain);
  }

  // GET_FILE_DATA is retained to read legacy desktop attachments (saved to disk
  // as absolute paths before uploads moved to the backend). New uploads go
  // through the backend over HTTP, so there is no longer a SAVE_FILE handler.
  ipcMain.handle(GET_FILE_DATA_CHANNEL_NAME, async (_event, filePath: string) => {
    try {
      const fileBuffer = fs.readFileSync(filePath);
      const base64Data = fileBuffer.toString("base64");

      const ext = path.extname(filePath).toLowerCase();
      const mimeTypes: Record<string, string> = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
      };
      if (!mimeTypes[ext]) {
        throw new Error(`Unsupported file extension: ${ext}`);
      }
      const mimeType = mimeTypes[ext];

      return `data:${mimeType};base64,${base64Data}`;
    } catch (error) {
      logger.error("Error getting file data:", error);
      throw error;
    }
  });

  // We can only create the window _after_ the handlers have been defined, because createWindow() invokes preload.ts
  // which depends on the handlers.
  await createWindow();

  // Main window exists now, so the migration's transient-window quit suppression
  // is no longer needed (any future window-all-closed is a real user close).
  isMigrating = false;

  // Initialize auto-updater (no-op for unpackaged/dev builds)
  autoUpdaterManager = initAutoUpdater(window!, store, () => {
    sendBackendState({ status: "shutting_down", payload: { message: "Installing update..." } });
  });

  // Renderer pulls initial auto-update status on mount, avoiding push race conditions.
  ipcMain.handle(GET_AUTO_UPDATE_STATUS_CHANNEL_NAME, () => {
    return autoUpdaterManager ? autoUpdaterManager.getStatus() : { type: "disabled" };
  });

  // Switch the logger from the temp file to the final location inside the
  // sculptor folder now that the data folder is known.
  finalizeLogger();

  const startTime = performance.now();

  let shouldStartBackend = !IS_DEVELOPMENT || process.env.START_BACKEND_IN_DEV;
  logger.info(
    `[main] backend startup: ${shouldStartBackend} (IS_DEV=${IS_DEVELOPMENT}, START_BACKEND_IN_DEV=${process.env.START_BACKEND_IN_DEV})`,
  );

  // In dev mode, SCULPTOR_CUSTOM_BACKEND_CMD env var overrides the store setting
  // and forces backend startup (since the custom command IS the backend)
  if (process.env.SCULPTOR_CUSTOM_BACKEND_CMD && !shouldStartBackend) {
    shouldStartBackend = true;
    logger.info("[main] SCULPTOR_CUSTOM_BACKEND_CMD set - forcing backend startup in dev mode");
  }

  if (shouldStartBackend) {
    const customCommand = process.env.SCULPTOR_CUSTOM_BACKEND_CMD || (store.get("customBackendCommand", "") as string);

    sendBackendState({ status: "loading", payload: { message: "Waiting for backend..." } });

    if (customCommand) {
      // Custom command mode: spawn user's command and parse URL from stdout
      isInCustomCommandMode = true;
      spawnCustomCommand(customCommand);
      // Note: resolveBackendUrl is called after parseUrlFromStdout succeeds

      const readinessTimeoutSec = store.get("backendReadinessTimeout", 60) as number;
      const readinessTimeoutMs = readinessTimeoutSec * 1000;

      try {
        customCommandBackendUrl = await parseUrlFromStdout(pythonBackgroundProcess!.stdout!, readinessTimeoutMs);
        resolveBackendUrl?.(customCommandBackendUrl);
        logger.info(`[main] parsed backend URL from custom command: ${customCommandBackendUrl}`);

        // After URL is found, pipe remaining stdout through
        pythonBackgroundProcess!.stdout?.on("data", (data) => {
          try {
            process.stdout.write(data);
          } catch {
            // Swallow
          }
        });
      } catch (err) {
        resolveBackendUrl?.(null);
        logger.error("[main] failed to parse URL from custom command:", err);
        sendBackendState({
          status: "error",
          payload: {
            message: `Custom command did not output a backend URL: ${(err as Error).message}`,
            stack: (err as Error).stack,
          },
        });
      }
    } else {
      // Default mode: not a custom command, resolve immediately
      resolveBackendUrl?.(null);

      // Default mode: spawn the packaged backend binary
      const shellPath = getShellPath();
      logger.info("[main] Using PATH:", shellPath);

      const { cmd, args } = await getBackendCommand();
      logger.info("[main] spawning backend without initial project:", cmd, args.join(" "));

      pythonBackgroundProcess = spawn(cmd, args, {
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          PATH: shellPath,
          SESSION_TOKEN: SESSION_TOKEN,
        },
        detached: true,
      });

      pythonBackgroundProcess.stdout?.on("data", (data) => {
        try {
          process.stdout.write(data);
        } catch {
          // Swallow — can fail if the app has crashed
        }
      });

      setupProcessHandlers(pythonBackgroundProcess);
    }

    logger.info("[main] backend process started, waiting for it to be ready...");
  } else {
    resolveBackendUrl?.(null);
    logger.info("[main] skipping starting the python backend (it should already be running)");
  }

  // Determine which URL to poll for health
  let isRunning: boolean;

  if (isInCustomCommandMode && customCommandBackendUrl) {
    const readinessTimeoutSec = store.get("backendReadinessTimeout", 60) as number;
    isRunning = await waitForBackend(customCommandBackendUrl, undefined, readinessTimeoutSec * 1000);
  } else {
    // In client_only mode, still try to connect to backend (which should be running remotely)
    isRunning = await waitForBackend(await PORT);
  }

  if (isRunning && !isQuitting) {
    restartCount = 0;
    const totalTime = performance.now() - startTime;

    if (shouldStartBackend) {
      logger.info(`[main] backend fully ready (total startup time: ${totalTime}ms)`);
    }

    if (isTracingEnabled()) {
      const backendBaseUrl =
        isInCustomCommandMode && customCommandBackendUrl ? customCommandBackendUrl : `http://127.0.0.1:${await PORT}`;
      setBackendUrlForTracing(backendBaseUrl);
      traceMark("electron.backend_ready");
    }

    sendBackendState({
      status: "running",
      payload: {
        message: "Backend is running.",
      },
    });
  } else {
    if (
      !isInPytest &&
      currentBackendStatus.status !== "error" &&
      currentBackendStatus.status !== "exited" &&
      !isQuitting
    ) {
      throw new Error("Tried to start the backend but it failed and we did not properly set our backend status.");
    }
  }
});

const cleanupBackendProcess = async (): Promise<void> => {
  try {
    // Flush any pending trace events to the backend BEFORE killing it, so
    // they land in the combined trace file the backend writes on exit.
    if (isTracingEnabled()) {
      traceMark("electron.shutdown_begin");
      await flushTracingBeforeExit();
    }

    if (pythonBackgroundProcess) {
      // With --trace-to active, the backend's lifespan teardown drains the
      // viztracer buffer and writes the combined Chrome JSON file. That can
      // take far longer than the default budget — without the extension the
      // SIGKILL fires while viztracer is still loading and the trace file is
      // never written.
      const baseGracePeriodMs = isInCustomCommandMode
        ? CUSTOM_COMMAND_SHUTDOWN_GRACE_PERIOD_MS
        : DEFAULT_BACKEND_SHUTDOWN_GRACE_PERIOD_MS;
      const gracePeriodMs = tracingTeardownGracePeriodMs(baseGracePeriodMs);
      await killProcessAndWait(pythonBackgroundProcess, gracePeriodMs);
    }
  } catch (error) {
    logger.error("Error killing backend process, sending SIGKILL:", error);
    pythonBackgroundProcess?.kill("SIGKILL");
  }
};

const shutdownBackend = async (statusMessage: string): Promise<void> => {
  isQuitting = true;
  sendBackendState({ status: "shutting_down", payload: { message: statusMessage } });
  await cleanupBackendProcess();
};

app.on("before-quit", async (e): Promise<void> => {
  logger.info("[main] before-quit fired, isQuitting=%s", isQuitting);
  if (isQuitting) return;

  e.preventDefault();

  try {
    const statusMessage = autoUpdaterManager?.isUpdating ? "Installing update..." : "Shutting down...";
    logger.info("[main] before-quit: %s", statusMessage);
    await shutdownBackend(statusMessage);
  } catch (error) {
    logger.error("[main] before-quit handler error, forcing quit:", error);
  }

  globalShortcut.unregisterAll();
  logger.info("[main] before-quit: calling app.quit()");
  app.quit();
});

function killProcessAndWait(proc: ReturnType<typeof spawn>, timeoutMs: number): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!proc || proc.killed) {
      resolve();
      return;
    }

    const timeout = setTimeout(() => {
      reject(new Error("Process kill timeout"));
    }, timeoutMs);

    proc.once("exit", () => {
      clearTimeout(timeout);
      resolve();
    });

    proc.once("error", (err) => {
      clearTimeout(timeout);
      reject(err);
    });

    proc.kill("SIGTERM");
  });
}

app.on("window-all-closed", (): void => {
  logger.info("[main] window-all-closed fired, isQuitting=%s, platform=%s", isQuitting, process.platform);

  // The one-time localStorage migration opens and closes a transient window
  // before the main window is created; its close leaves zero windows. Ignore
  // that so the app doesn't quit itself mid-startup (the main window is on its
  // way). Cleared once createWindow() returns.
  if (isMigrating) {
    logger.info("[main] window-all-closed during migration — ignoring");
    return;
  }

  if (IS_DEVELOPMENT && isQuitting) {
    // In dev mode, CTRL-C kills the Vite dev server simultaneously, crashing
    // the renderer and closing the window outside of app.quit()'s control.
    // This breaks Chromium's quit state machine — will-quit never fires.
    // Force exit since there's no backend process to clean up in dev mode.
    logger.info("[main] dev mode: quit sequence stalled, forcing exit");
    app.exit(0);
    return;
  }

  if (!isQuitting) {
    app.quit();
  }
});

// Handle terminal signals (Ctrl+C, kill, hangup) — skip the confirmation dialog
// and go straight to cleanup so the child process (e.g. Docker container) is stopped.
// SIGHUP is sent by tmux when a session/pane is killed.
const makeSignalHandler = (signalName: string) => (): void => {
  logger.info("[main] received %s signal, isQuitting=%s", signalName, isQuitting);
  if (isQuitting) return;
  isQuitting = true;

  logger.info("[main] handling %s — shutting down (bypassing before-quit dialog)", signalName);
  sendBackendState({ status: "shutting_down", payload: { message: "Shutting down..." } });
  globalShortcut.unregisterAll();

  cleanupBackendProcess()
    .catch((error) => {
      logger.error("[main] cleanup failed during %s handling:", signalName, error);
    })
    .finally(() => {
      logger.info("[main] calling app.exit(0) after %s cleanup", signalName);
      app.exit(0);
    });
};

// Note: SIGINT/SIGTERM/SIGHUP handlers below are overridden by Chromium's C++
// signal handler (electron_browser_main_parts_posix.cc) which calls Browser::Quit()
// directly, firing `before-quit` instead. These Node.js handlers are effectively
// dead code but kept as documentation of intent.
process.on("SIGINT", makeSignalHandler("SIGINT"));
process.on("SIGTERM", makeSignalHandler("SIGTERM"));
process.on("SIGHUP", makeSignalHandler("SIGHUP"));

app.on("will-quit", (e) => {
  logger.info("[main] will-quit fired, isQuitting=%s, defaultPrevented=%s", isQuitting, e.defaultPrevented);
});

app.on("quit", (_e, exitCode) => {
  logger.info("[main] quit fired, exitCode=%s", exitCode);
});

// This gets triggered when user clicks the app icon in the Dock in macOS.
app.on("activate", () => {
  if (window !== null) {
    window.show();
    window.focus();
  }
});
