import { beforeEach, describe, expect, it } from "vitest";

import { migrateLegacyExtensionStorage } from "./extensionRegistry.ts";

// Importing the registry runs the migration once at module init (against
// whatever localStorage held at import time); each test below seeds storage
// explicitly and invokes the migration directly.
describe("migrateLegacyExtensionStorage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  const migrate = (): void => migrateLegacyExtensionStorage(window.localStorage);

  it("copies each persisted source-list key to its new name, leaving the old key in place", () => {
    window.localStorage.setItem("sculptor-plugin-sources", JSON.stringify(["http://localhost:5174/my-extension"]));
    window.localStorage.setItem("sculptor-plugin-disabled-sources", JSON.stringify(["/plugins/sculpty"]));
    window.localStorage.setItem("sculptor-plugin-enabled-sources", JSON.stringify(["/plugins/pomodoro"]));

    migrate();

    expect(window.localStorage.getItem("sculptor-extension-sources")).toBe(
      JSON.stringify(["http://localhost:5174/my-extension"]),
    );
    expect(window.localStorage.getItem("sculptor-extension-disabled-sources")).toBe(
      JSON.stringify(["/extensions/sculpty"]),
    );
    expect(window.localStorage.getItem("sculptor-extension-enabled-sources")).toBe(
      JSON.stringify(["/extensions/pomodoro"]),
    );
    // The old keys stay so an older build sharing this origin still finds them.
    expect(window.localStorage.getItem("sculptor-plugin-sources")).toBe(
      JSON.stringify(["http://localhost:5174/my-extension"]),
    );
  });

  it("rewrites backend-served /plugins/ paths but not absolute URLs", () => {
    window.localStorage.setItem(
      "sculptor-plugin-sources",
      JSON.stringify(["/plugins/local/my-extension", "/plugins/local/dev/ws1/tool", "http://example.com/plugins/x"]),
    );

    migrate();

    expect(window.localStorage.getItem("sculptor-extension-sources")).toBe(
      JSON.stringify([
        "/extensions/local/my-extension",
        "/extensions/local/dev/ws1/tool",
        // A `/plugins/` path inside a foreign origin's URL is that server's
        // layout, not the host's static mount.
        "http://example.com/plugins/x",
      ]),
    );
  });

  it("never overwrites a value already written under the new key", () => {
    window.localStorage.setItem("sculptor-plugin-sources", JSON.stringify(["/plugins/old"]));
    window.localStorage.setItem("sculptor-extension-sources", JSON.stringify(["/extensions/new"]));

    migrate();

    expect(window.localStorage.getItem("sculptor-extension-sources")).toBe(JSON.stringify(["/extensions/new"]));
  });

  it("copies a malformed source-list value verbatim rather than dropping it", () => {
    window.localStorage.setItem("sculptor-plugin-sources", "not json");

    migrate();

    expect(window.localStorage.getItem("sculptor-extension-sources")).toBe("not json");
  });

  it("sweeps every per-extension setting under the legacy namespace", () => {
    window.localStorage.setItem("sculptor-plugin:linear-issue:apiKey", JSON.stringify("secret"));
    window.localStorage.setItem("sculptor-plugin:linear-issue:teamId", JSON.stringify("team-1"));
    // A key that merely shares the hyphenated prefix is not a setting.
    window.localStorage.setItem("sculptor-plugin-renderer-id", "abc");

    migrate();

    expect(window.localStorage.getItem("sculptor-extension:linear-issue:apiKey")).toBe(JSON.stringify("secret"));
    expect(window.localStorage.getItem("sculptor-extension:linear-issue:teamId")).toBe(JSON.stringify("team-1"));
    expect(window.localStorage.getItem("sculptor-extension-renderer-id")).toBeNull();
    // Legacy settings stay in place for older builds on the same origin.
    expect(window.localStorage.getItem("sculptor-plugin:linear-issue:apiKey")).toBe(JSON.stringify("secret"));
  });

  it("keeps an already-written new setting over the legacy one", () => {
    window.localStorage.setItem("sculptor-plugin:linear-issue:apiKey", JSON.stringify("old"));
    window.localStorage.setItem("sculptor-extension:linear-issue:apiKey", JSON.stringify("new"));

    migrate();

    expect(window.localStorage.getItem("sculptor-extension:linear-issue:apiKey")).toBe(JSON.stringify("new"));
  });

  it("is a no-op when nothing legacy is stored", () => {
    migrate();
    expect(window.localStorage.length).toBe(0);
  });
});
