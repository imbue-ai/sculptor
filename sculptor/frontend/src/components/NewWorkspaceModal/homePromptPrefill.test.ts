import { describe, expect, it } from "vitest";

import type { SculptorSettings } from "../../api";
import { shouldPrefillHomePrompt } from "./homePromptPrefill.ts";

// All SculptorSettings fields are optional, so these minimal objects are valid.
const PRODUCTION_SETTINGS: SculptorSettings = {};
const INTEGRATION_SETTINGS: SculptorSettings = { TESTING: { INTEGRATION_ENABLED: true } };
const INTEGRATION_DISABLED_SETTINGS: SculptorSettings = { TESTING: { INTEGRATION_ENABLED: false } };

describe("shouldPrefillHomePrompt", () => {
  it("prefills the inline Home form once settings have loaded outside integration tests", () => {
    expect(
      shouldPrefillHomePrompt({ entrySource: "home", settings: PRODUCTION_SETTINGS, hasAlreadyPrefilled: false }),
    ).toBe(true);
  });

  it("prefills when integration testing is explicitly disabled", () => {
    expect(
      shouldPrefillHomePrompt({
        entrySource: "home",
        settings: INTEGRATION_DISABLED_SETTINGS,
        hasAlreadyPrefilled: false,
      }),
    ).toBe(true);
  });

  it("never prefills for the modal entry sources", () => {
    for (const entrySource of ["palette", "keybinding", "topbar"] as const) {
      expect(shouldPrefillHomePrompt({ entrySource, settings: PRODUCTION_SETTINGS, hasAlreadyPrefilled: false })).toBe(
        false,
      );
    }
  });

  it("waits for settings to load before deciding (null settings → no prefill)", () => {
    expect(shouldPrefillHomePrompt({ entrySource: "home", settings: null, hasAlreadyPrefilled: false })).toBe(false);
  });

  it("does not prefill under integration testing", () => {
    expect(
      shouldPrefillHomePrompt({ entrySource: "home", settings: INTEGRATION_SETTINGS, hasAlreadyPrefilled: false }),
    ).toBe(false);
  });

  it("is one-shot — does not re-apply once it has already prefilled this mount", () => {
    expect(
      shouldPrefillHomePrompt({ entrySource: "home", settings: PRODUCTION_SETTINGS, hasAlreadyPrefilled: true }),
    ).toBe(false);
  });
});
