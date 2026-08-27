import { describe, expect, it } from "vitest";

import { SETTINGS_SECTIONS } from "~/pages/settings/sections.ts";

/**
 * Drift guardrail for `Harness.configuration_settings_section()` (backend). Each harness
 * returns a frontend `SettingsSection` id as a bare string (that enum is frontend-only),
 * which the composer's "Go to harness configuration" CTA routes through `useOpenSettings`.
 * If a section is renamed or removed from `SETTINGS_SECTIONS` without updating the harness,
 * this fails instead of silently routing nowhere.
 *
 * Mirror of the values the backend can emit — add a harness's destination here when it
 * overrides `configuration_settings_section()` (see `interfaces/agents/harness.py` and
 * the per-harness overrides).
 */
const HARNESS_CONFIG_DESTINATIONS = ["DEPENDENCIES", "PI"] as const;

describe("Harness configuration destination drift", () => {
  it("every harness configuration destination is a real SettingsSection id", () => {
    const sectionIds = new Set<string>(SETTINGS_SECTIONS.map((section) => section.id));
    for (const destination of HARNESS_CONFIG_DESTINATIONS) {
      expect(sectionIds.has(destination)).toBe(true);
    }
  });
});
