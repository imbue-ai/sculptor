import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";

import { BrowserWindow } from "electron";

import { APP_ORIGIN } from "./appProtocol";
import { buildWriteScript, MIGRATION_BLANK_PATH, READ_SCRIPT } from "./localStorageMigrationLogic";
import { logger } from "./logger";

// Re-exported so main.ts can register the sentinel route from a single import.
export { MIGRATION_BLANK_PATH } from "./localStorageMigrationLogic";

// electron-store flags live in userData (origin-independent), so the migration
// runs at most once. Versioned in case we ever need a second pass.
const DONE_KEY = "localStorageOriginMigration.v1.done";
const ATTEMPTS_KEY = "localStorageOriginMigration.v1.attempts";
const MAX_ATTEMPTS = 3;

// Minimal structural type so this module doesn't couple to electron-store.
type MigrationStore = {
  get(key: string): unknown;
  set(key: string, value: unknown): void;
  delete(key: string): void;
};

/**
 * One-time migration of renderer localStorage from the legacy file:// origin
 * (opaque — all file URLs share the single "file://" storage key) to the new
 * sculptor://app origin. localStorage is partitioned by origin, so without this
 * an in-place upgrade resets layout, theme, tabs, zoom, plugin sources, etc.
 *
 * No API reads another origin's localStorage, so we do it at the web layer:
 * load a throwaway file:// doc to read, then the sculptor://app blank sentinel
 * to write — both in one hidden window on the default session (the same
 * userData partition that holds the old data). Must run before the main window
 * loads sculptor://app. Never throws; the app starts regardless.
 */
export async function migrateLocalStorageToAppScheme(store: MigrationStore): Promise<void> {
  if (store.get(DONE_KEY) === true) return;

  const attempts = (store.get(ATTEMPTS_KEY) as number | undefined) ?? 0;
  if (attempts >= MAX_ATTEMPTS) {
    logger.warn(`[migration] giving up localStorage origin migration after ${attempts} attempts`);
    store.set(DONE_KEY, true);
    return;
  }
  store.set(ATTEMPTS_KEY, attempts + 1);

  const startedAt = Date.now();
  let tmpDir: string | null = null;
  // Hidden, default session (so it sees the old file:// partition), no preload.
  const win = new BrowserWindow({
    show: false,
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  try {
    // 1. Read the legacy file:// partition. Any file:// document shares the
    //    "file://" storage key, so load a blank temp file rather than the real
    //    index.html (which would boot the app and race our write).
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sculptor-ls-mig-"));
    const blank = path.join(tmpDir, "blank.html");
    fs.writeFileSync(blank, '<!doctype html><meta charset="utf-8">');
    await win.loadURL(pathToFileURL(blank).toString());
    const data = JSON.parse(await win.webContents.executeJavaScript(READ_SCRIPT)) as Record<string, string>;

    const total = Object.keys(data).length;
    if (total === 0) {
      logger.info("[migration] no legacy file:// localStorage to migrate");
      store.set(DONE_KEY, true);
      store.delete(ATTEMPTS_KEY);
      return;
    }

    // 2. Write into the sculptor://app partition via the blank sentinel doc.
    await win.loadURL(`${APP_ORIGIN}${MIGRATION_BLANK_PATH}`);
    const written = (await win.webContents.executeJavaScript(buildWriteScript(data))) as number;

    logger.info(
      `[migration] migrated ${written}/${total} localStorage keys to ${APP_ORIGIN} in ${Date.now() - startedAt}ms`,
    );
    store.set(DONE_KEY, true);
    store.delete(ATTEMPTS_KEY);
  } catch (error) {
    // Don't set the done flag — a transient failure retries next launch, capped
    // by MAX_ATTEMPTS. The app still starts; worst case is the cosmetic reset.
    logger.error(`[migration] localStorage origin migration failed: ${String(error)}`);
  } finally {
    if (!win.isDestroyed()) win.destroy();
    if (tmpDir !== null) fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}
