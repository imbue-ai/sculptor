import type { BrowserWindow } from "electron";
import { app, ipcMain } from "electron";
import type Store from "electron-store";
import { autoUpdater } from "electron-updater";
import semver from "semver";

import type { AutoUpdateStatus, UpdateChannel } from "../shared/types";
import {
  AUTO_UPDATE_CHECK_CHANNEL_NAME,
  AUTO_UPDATE_INSTALL_CHANNEL_NAME,
  AUTO_UPDATE_SET_CHANNEL_CHANNEL_NAME,
  AUTO_UPDATE_STATUS_CHANNEL_NAME,
} from "./constants";
import { logger } from "./logger";

const S3_BASE_URL =
  process.env.SCULPTOR_TEST_OVERRIDE_BASE_URL ?? "https://imbue-sculptor-releases.s3.us-west-2.amazonaws.com";
const CHECK_INTERVAL_MS = 30 * 60 * 1000; // 30 minutes

class AutoUpdaterManager {
  private window: BrowserWindow;
  private store: Store;
  private checkIntervalId: ReturnType<typeof setInterval>;
  private currentChannel: UpdateChannel;
  private lastStatus: AutoUpdateStatus;
  private onBeforeInstall: (() => void) | undefined;
  isUpdating = false;

  constructor(window: BrowserWindow, store: Store, onBeforeInstall?: () => void) {
    this.window = window;
    this.store = store;
    this.onBeforeInstall = onBeforeInstall;

    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = false;
    autoUpdater.allowDowngrade = false;
    autoUpdater.logger = logger;

    autoUpdater.requestHeaders = {
      "User-Agent": `Sculptor/${app.getVersion()} (${process.platform}; ${process.arch})`,
    };

    // In test mode, tell electron-updater to bypass its own app.isPackaged guard.
    if (process.env.SCULPTOR_TEST_OVERRIDE_PACKAGED) {
      autoUpdater.forceDevUpdateConfig = true;
    }

    this.currentChannel = this.store.get("updateChannel", "STABLE") as UpdateChannel;
    this.lastStatus = { type: "checking", channel: this.currentChannel };
    autoUpdater.setFeedURL({
      provider: "generic",
      url: this.getFeedUrl(this.currentChannel),
    });

    this.registerEventHandlers();
    this.registerIpcHandlers();

    autoUpdater.checkForUpdates().catch((err) => {
      logger.error("[auto-updater] Initial check failed:", err);
      this.sendStatus({ type: "error", channel: this.currentChannel, message: err.message });
    });

    this.checkIntervalId = setInterval(() => {
      autoUpdater.checkForUpdates().catch((err) => {
        logger.error("[auto-updater] Periodic check failed:", err);
        this.sendStatus({ type: "error", channel: this.currentChannel, message: err.message });
      });
    }, CHECK_INTERVAL_MS);
  }

  private getFeedUrl(channel: UpdateChannel): string {
    const channelPrefix = channel === "STABLE" ? "slim" : "slim-rc";
    let platformPath: string;
    if (process.platform === "darwin") {
      platformPath = "zip/darwin/arm64";
    } else {
      const arch = process.arch === "arm64" ? "arm64" : "x64";
      platformPath = `AppImage/${arch}`;
    }
    return `${S3_BASE_URL}/${channelPrefix}/${platformPath}`;
  }

  private sendStatus(status: AutoUpdateStatus): void {
    this.lastStatus = status;
    this.window.webContents.send(AUTO_UPDATE_STATUS_CHANNEL_NAME, status);
  }

  getStatus(): AutoUpdateStatus {
    return this.lastStatus;
  }

  private registerEventHandlers(): void {
    autoUpdater.on("update-available", async (info) => {
      this.sendStatus({ type: "available", channel: this.currentChannel, version: info.version });
      try {
        await autoUpdater.downloadUpdate();
      } catch (err) {
        logger.error("[auto-updater] Download failed:", err);
        this.sendStatus({ type: "error", channel: this.currentChannel, message: (err as Error).message });
      }
    });

    autoUpdater.on("download-progress", (progressObj) => {
      this.sendStatus({ type: "downloading", channel: this.currentChannel, percent: Math.round(progressObj.percent) });
    });

    autoUpdater.on("update-downloaded", (info) => {
      this.sendStatus({ type: "ready", channel: this.currentChannel, version: info.version });
    });

    autoUpdater.on("error", (error) => {
      logger.error("[auto-updater] Error:", error);
      this.sendStatus({ type: "error", channel: this.currentChannel, message: error.message });
    });

    autoUpdater.on("update-not-available", (info) => {
      const currentVersion = app.getVersion();
      if (semver.valid(info.version) && semver.valid(currentVersion) && semver.lt(info.version, currentVersion)) {
        this.sendStatus({ type: "idle", channel: this.currentChannel, latestChannelVersion: info.version });
      } else {
        this.sendStatus({ type: "idle", channel: this.currentChannel });
      }
    });
  }

  private registerIpcHandlers(): void {
    ipcMain.handle(AUTO_UPDATE_INSTALL_CHANNEL_NAME, (): boolean => {
      if (this.lastStatus.type !== "ready") {
        logger.warn(`[auto-updater] Install requested but status is "${this.lastStatus.type}", ignoring`);
        return false;
      }
      this.isUpdating = true;
      this.onBeforeInstall?.();
      autoUpdater.quitAndInstall(false, true);
      return true;
    });

    ipcMain.handle(AUTO_UPDATE_CHECK_CHANNEL_NAME, async () => {
      this.sendStatus({ type: "checking", channel: this.currentChannel });
      try {
        await autoUpdater.checkForUpdates();
      } catch (err) {
        logger.error("[auto-updater] Manual check failed:", err);
        this.sendStatus({ type: "error", channel: this.currentChannel, message: (err as Error).message });
      }
    });

    ipcMain.handle(AUTO_UPDATE_SET_CHANNEL_CHANNEL_NAME, async (_event, channel: UpdateChannel) => {
      this.currentChannel = channel;
      this.store.set("updateChannel", channel);
      this.sendStatus({ type: "idle", channel: this.currentChannel });

      autoUpdater.setFeedURL({
        provider: "generic",
        url: this.getFeedUrl(channel),
      });

      this.sendStatus({ type: "checking", channel: this.currentChannel });
      try {
        await autoUpdater.checkForUpdates();
      } catch (err) {
        logger.error("[auto-updater] Channel switch check failed:", err);
        this.sendStatus({ type: "error", channel: this.currentChannel, message: (err as Error).message });
      }
    });
  }

  dispose(): void {
    clearInterval(this.checkIntervalId);
  }
}

export function initAutoUpdater(
  window: BrowserWindow,
  store: Store,
  onBeforeInstall?: () => void,
): AutoUpdaterManager | null {
  // Kill switch: setting SCULPTOR_DISABLE_AUTO_UPDATE to any non-empty value
  // prevents the auto-updater from initializing regardless of other flags.
  if (process.env.SCULPTOR_DISABLE_AUTO_UPDATE) {
    logger.info("[auto-updater] Skipping: SCULPTOR_DISABLE_AUTO_UPDATE is set");
    return null;
  }

  // SCULPTOR_TEST_OVERRIDE_PACKAGED: for unpackaged dev builds — bypasses
  // both guards and sets forceDevUpdateConfig so electron-updater works
  // without a real packaged app.
  // SCULPTOR_TEST_SKIP_DEV_VERSION_GUARD: for packaged dev builds — only
  // bypasses the dev-version guard so the auto-updater initializes, but
  // does NOT set forceDevUpdateConfig (the app is already packaged).
  const isDevTestMode = !!process.env.SCULPTOR_TEST_OVERRIDE_PACKAGED;
  const shouldSkipDevGuard = isDevTestMode || !!process.env.SCULPTOR_TEST_SKIP_DEV_VERSION_GUARD;

  if (!isDevTestMode && !app.isPackaged) {
    logger.info("[auto-updater] Skipping: app is not packaged");
    return null;
  }

  if (!shouldSkipDevGuard && app.getVersion().includes("dev")) {
    logger.info("[auto-updater] Skipping: dev version");
    return null;
  }

  return new AutoUpdaterManager(window, store, onBeforeInstall);
}
