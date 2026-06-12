import * as fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { app } from "electron";
import log from "electron-log";

/**
 * Return the Sculptor data folder, matching the backend's get_sculptor_folder() in
 * sculptor/utils/build.py.
 *
 * Resolution order:
 * 1. SCULPTOR_FOLDER env var override
 * 2. Dev (unpackaged): <repo_root>/.dev_sculptor
 * 3. Packaged dev build (.dev version): ~/.dev-sculptor
 * 4. Packaged production: ~/.sculptor
 */
export const getSculptorFolder = (): string => {
  const fromEnv = process.env.SCULPTOR_FOLDER;
  if (fromEnv) {
    return fromEnv;
  }

  if (!app.isPackaged) {
    // SCULPTOR_FRONTEND_DIR is set to $PWD (sculptor/frontend) by the electron:start script.
    const frontendDir = process.env.SCULPTOR_FRONTEND_DIR;
    if (frontendDir) {
      return path.join(frontendDir, "..", "..", ".dev_sculptor");
    }
    // Fallback when SCULPTOR_FRONTEND_DIR isn't available.
    return path.join(os.homedir(), ".dev-sculptor");
  }

  // Packaged dev builds have a version like "0.10.0-dev.0" (semver form of PEP 440 .dev suffix).
  const version = app.getVersion();
  if (version.includes("-dev.")) {
    return path.join(os.homedir(), ".dev-sculptor");
  }

  return path.join(os.homedir(), ".sculptor");
};

const FINAL_LOG_PATH = path.join(getSculptorFolder(), "internal", "logs", "electron", "electron.log");
export const TEMP_LOG_PATH = path.join(os.tmpdir(), `sculptor-premigration-${process.pid}.log`);

// Start logging to a temp file so we don't create directories under the
// sculptor folder before migration has a chance to run.
log.transports.file.level = "info";
log.transports.file.maxSize = 100 * 1024 * 1024; // 100MB
log.transports.file.resolvePathFn = (): string => TEMP_LOG_PATH;
log.transports.console.level = "debug";

log.info(`Logging to temp file: ${TEMP_LOG_PATH}`);

/**
 * Switch the file transport to the final log path and seed the final log
 * with everything captured in the temp file. Call this after migration has
 * completed (or been skipped).
 *
 * We write the temp contents to the final path *before* redirecting
 * electron-log, so there is no window where both electron-log and our
 * fs.writeFileSync are racing on the same file.
 */
export const finalizeLogger = (): void => {
  try {
    // Ensure the final log directory exists
    fs.mkdirSync(path.dirname(FINAL_LOG_PATH), { recursive: true });

    // Append temp contents to the final log so the full startup sequence
    // is captured alongside any existing historical log data.
    // electron-log terminates every line with \n, so both the existing file
    // and temp contents will end with newlines  -- no separator needed.
    if (fs.existsSync(TEMP_LOG_PATH)) {
      const tempContents = fs.readFileSync(TEMP_LOG_PATH, "utf8");
      if (tempContents.length > 0) {
        fs.appendFileSync(FINAL_LOG_PATH, tempContents);
      }
      fs.unlinkSync(TEMP_LOG_PATH);
    }
  } catch (err) {
    // Non-fatal  -- we'll still switch to the final path and keep logging.
    log.warn(`Failed to seed final log with temp contents: ${err}`);
  }

  // Now redirect electron-log. It will append to the file we just created.
  log.transports.file.resolvePathFn = (): string => FINAL_LOG_PATH;
  log.info(`Switched log output to: ${FINAL_LOG_PATH}`);
};

export { log as logger };
