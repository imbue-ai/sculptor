/** Tests for the localStorage origin-migration logic.
 *
 * These cover the two pure helpers that are serialized (via Function.toString())
 * into the scripts the migration runs in the renderer — so asserting them here
 * asserts exactly the code that ships. The Electron orchestration in
 * `migrateLocalStorageToAppScheme` (hidden window, two loadURLs) is not unit
 * tested; it's covered by the manual packaged-app upgrade check.
 */
import { describe, expect, it } from "vitest";

import {
  applyMigratedEntries,
  DENY_PREFIXES,
  MIGRATION_BLANK_PATH,
  selectMigratableEntries,
} from "./localStorageMigrationLogic";

const entriesOf = (obj: Record<string, string>): Array<[string, string]> => Object.entries(obj);

type FakeStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  snapshot(): Record<string, string>;
};

// Minimal Storage stand-in: items in a Map, getItem/setItem only (the surface
// applyMigratedEntries uses), plus a snapshot for assertions.
const makeStorage = (initial: Record<string, string> = {}): FakeStorage => {
  const map = new Map<string, string>(Object.entries(initial));
  return {
    getItem: (key: string): string | null => (map.has(key) ? (map.get(key) as string) : null),
    setItem: (key: string, value: string): void => {
      map.set(key, value);
    },
    snapshot: (): Record<string, string> => Object.fromEntries(map),
  };
};

describe("selectMigratableEntries", () => {
  it("keeps app keys across the various ad-hoc prefixes", () => {
    const input = {
      "sculptor-tabs": "1",
      "sculptor.telemetryOptedOut": "true",
      "chat.toolDensity": "compact",
      "browser-panel-state-ws_abc": "{}",
      "diffPanel-markdownRenderMode": "rendered",
      lastUsedAgentType: "claude",
    };
    expect(selectMigratableEntries(entriesOf(input), DENY_PREFIXES)).toEqual(input);
  });

  it("drops posthog and sentry SDK keys, case-insensitively", () => {
    const input = {
      "sculptor-tabs": "1",
      ph_token_posthog: "{}",
      __ph_opt_in_out_token: "1",
      sentryReplaySession: "x",
      PH_TOKEN_posthog: "{}",
      "Sentry-extra": "y",
    };
    expect(selectMigratableEntries(entriesOf(input), DENY_PREFIXES)).toEqual({ "sculptor-tabs": "1" });
  });

  it("returns an empty object when there is nothing to migrate", () => {
    expect(selectMigratableEntries([], DENY_PREFIXES)).toEqual({});
    expect(selectMigratableEntries(entriesOf({ ph_x: "1", __ph_y: "2" }), DENY_PREFIXES)).toEqual({});
  });
});

describe("applyMigratedEntries", () => {
  it("writes only keys absent in the target and returns the count", () => {
    const storage = makeStorage({ "sculptor-tabs": "existing" });
    const written = applyMigratedEntries(storage, {
      "sculptor-tabs": "incoming", // present -> skipped (non-clobber)
      "chat.toolDensity": "compact", // absent -> written
      lastUsedAgentType: "claude", // absent -> written
    });
    expect(written).toBe(2);
    expect(storage.snapshot()).toEqual({
      "sculptor-tabs": "existing",
      "chat.toolDensity": "compact",
      lastUsedAgentType: "claude",
    });
  });

  it("preserves values verbatim, including JSON blobs", () => {
    const storage = makeStorage();
    const blob = JSON.stringify({ order: [{ tabId: "t1" }], activeIndex: 0 });
    applyMigratedEntries(storage, { "sculptor-tabs": blob });
    expect(storage.getItem("sculptor-tabs")).toBe(blob);
  });

  it("writes nothing for empty data", () => {
    const storage = makeStorage({ a: "1" });
    expect(applyMigratedEntries(storage, {})).toBe(0);
    expect(storage.snapshot()).toEqual({ a: "1" });
  });
});

describe("migration constants", () => {
  it("serves the blank sentinel from an extensionless app-origin path", () => {
    // Extensionless so the app-scheme SPA fallback never turns it into a 404.
    expect(MIGRATION_BLANK_PATH.startsWith("/")).toBe(true);
    expect(MIGRATION_BLANK_PATH).not.toContain(".");
  });
});
