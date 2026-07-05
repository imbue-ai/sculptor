/**
 * Pure helpers for the localStorage origin migration (file:// -> sculptor://app).
 *
 * Electron-free on purpose — like appProtocol.ts — so the security/correctness
 * logic is unit-testable without an Electron runtime. The orchestration that
 * actually drives a hidden window lives in localStorageMigration.ts.
 */

// Sentinel path the app-scheme handler serves as a blank document (see
// registerAppProtocolHandler in main.ts). Lets the migration open a page on the
// sculptor://app origin to *write* localStorage without booting the renderer.
// Extensionless so the handler's SPA fallback never turns a miss into a 404.
export const MIGRATION_BLANK_PATH = "/__origin_migration_blank";

// Migrate every renderer localStorage key EXCEPT third-party SDK state, which
// is better left to re-initialize on the new origin. An allowlist is unsafe
// here: the app stores under many ad-hoc prefixes (sculptor-*, browser-panel-
// state-*, chat.*, diffPanel-*, lastUsedAgentType, ...) and most keys are built
// dynamically, so any fixed list would silently drop state. Copying a stale key
// is harmless (it was already in the old partition; nothing reads it); missing
// a live one is the regression we're preventing. Compared lowercased.
//   - ph_* / __ph*  : posthog-js distinct_id, feature flags, opt-in/out state
//   - sentry*       : Sentry SDK state
// The app's own telemetry mirror (sculptor.telemetryOptedOut) is NOT an SDK key
// and is migrated, so Sentry's pre-handshake beforeSend respects the opt-out.
export const DENY_PREFIXES = ["ph_", "__ph", "sentry"];

// The minimal Storage surface applyMigratedEntries touches.
type WritableStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

/**
 * Keep every entry except SDK-managed keys (prefix match, lowercased).
 *
 * Serialized verbatim into READ_SCRIPT via Function.toString(), so the unit
 * tests exercise exactly the shipped logic. It must therefore stay
 * self-contained — reference only its parameters and JS globals, never a
 * module-scope binding (toString() does not capture closures).
 */
export const selectMigratableEntries = (
  entries: Array<[string, string]>,
  denyPrefixes: Array<string>,
): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const [key, value] of entries) {
    const lower = key.toLowerCase();
    if (!denyPrefixes.some((prefix) => lower.startsWith(prefix))) {
      out[key] = value;
    }
  }
  return out;
};

/**
 * Write each entry only when its key is absent (non-clobber), so a user who
 * already launched the new build keeps newer values. Returns the count written.
 *
 * Same serialization contract as selectMigratableEntries — keep self-contained.
 */
export const applyMigratedEntries = (storage: WritableStorage, data: Record<string, string>): number => {
  let written = 0;
  for (const key of Object.keys(data)) {
    if (storage.getItem(key) === null) {
      storage.setItem(key, data[key]);
      written += 1;
    }
  }
  return written;
};

// Read all localStorage in the page, minus SDK keys, as a JSON string. Built
// from the function source so it cannot drift from the unit-tested logic.
export const READ_SCRIPT = `JSON.stringify((${selectMigratableEntries.toString()})(Object.entries(localStorage), ${JSON.stringify(DENY_PREFIXES)}))`;

// Write the migrated entries (non-clobber) into the page's localStorage.
export const buildWriteScript = (data: Record<string, string>): string =>
  `(${applyMigratedEntries.toString()})(localStorage, ${JSON.stringify(data)})`;
