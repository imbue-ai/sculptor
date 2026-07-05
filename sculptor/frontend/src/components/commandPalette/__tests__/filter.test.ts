import { describe, expect, it } from "vitest";

import { buildItemValue, makePaletteFilter, paletteFilter, ROW_VALUE_SEP } from "../utils/filter.ts";

describe("paletteFilter", () => {
  it("returns a positive score for empty queries (all rows visible)", () => {
    expect(paletteFilter("Open Settings__open.settings", "")).toBeGreaterThan(0);
    expect(paletteFilter("Open Settings__open.settings", "   ")).toBeGreaterThan(0);
  });

  it("ranks exact > prefix > word-prefix > substring > subsequence", () => {
    const exact = paletteFilter("settings__open.settings", "settings");
    const prefix = paletteFilter("Settings page__open.settings", "settings");
    const wordPrefix = paletteFilter("Open Settings__open.settings", "settings");
    // No word boundary in front of "settings" — substring tier only.
    const substring = paletteFilter("AwesomesettingsBar__x", "settings");
    const subseq = paletteFilter("Compose a setting tweak__y", "setings");
    expect(exact).toBeGreaterThan(prefix);
    expect(prefix).toBeGreaterThan(wordPrefix);
    expect(wordPrefix).toBeGreaterThan(substring);
    expect(substring).toBeGreaterThan(subseq);
  });

  it("regression: 'light' ranks Light above 'Toggle Right Panel'", () => {
    // Real bug: typing 'light' was surfacing Toggle Right Panel because
    // 'right' contains the in-order subsequence 'ight'. Title-tier scoring
    // makes the exact title match dominate any subsequence hit.
    const lightExact = paletteFilter("Light__theme.appearance.light", "light");
    const rightSubseq = paletteFilter("Toggle Right Panel__view.toggle_right", "light");
    expect(lightExact).toBeGreaterThan(rightSubseq);
  });

  it("keyword matches cannot beat title prefix matches", () => {
    // Title prefix should beat a keyword exact match — keywords are
    // capped at the substring tier so they can't overpower titles.
    const titlePrefix = paletteFilter("Hello world__a", "hel");
    const keywordExact = paletteFilter("Other thing__b", "hel", ["hel"]);
    expect(titlePrefix).toBeGreaterThan(keywordExact);
  });

  it("returns 0 for queries with no character match", () => {
    expect(paletteFilter("Open Settings__open.settings", "xyz")).toBe(0);
  });
});

describe("buildItemValue + paletteFilter round-trip", () => {
  it("strips the id suffix when ranking — query should not match the id slug alone", () => {
    const value = buildItemValue({ title: "Open Settings", id: "nav.settings" });
    const titleScore = paletteFilter(value, "open");
    const idScore = paletteFilter(value, "nav");
    expect(titleScore).toBeGreaterThan(idScore);
  });

  it("encodes the id with a separator that we can split on", () => {
    const value = buildItemValue({ title: "Foo", id: "bar.baz" });
    expect(value).toContain(ROW_VALUE_SEP);
    expect(value.split(ROW_VALUE_SEP)).toEqual(["Foo", "bar.baz"]);
  });

  it("uses keywords passed by cmdk as the secondary haystack", () => {
    const value = buildItemValue({ title: "Toggle Dev Panel", id: "developer.dev_panel" });
    const score = paletteFilter(value, "debug", ["debug"]);
    expect(score).toBeGreaterThan(0);
  });
});

describe("makePaletteFilter", () => {
  const lightValue = buildItemValue({ title: "Light", id: "theme.appearance.light" });
  const rightValue = buildItemValue({ title: "Toggle Right Panel", id: "view.toggle_right" });
  const switchValue = buildItemValue({ title: "Go to Workspace...", id: "workspaces.switch" });
  const otherValue = buildItemValue({ title: "Go to agent...", id: "agents.switch" });

  it("regression: penalty does NOT reorder light below toggle right panel", () => {
    // The page-scoped penalty (×0.25) used to crush Light's exact title
    // match (1.0 → 0.25) below Toggle Right Panel's subsequence match
    // (~0.46). With wide tiers, exact 1000 × 0.25 = 250 still beats any
    // subsequence (≤ 2.0).
    const filter = makePaletteFilter({
      isPageScoped: (id) => id.startsWith("theme.appearance."),
      isAtRoot: true,
    });
    expect(filter(lightValue, "light")).toBeGreaterThan(filter(rightValue, "light"));
  });

  it("primary boost lifts page-openers within their tier", () => {
    // Both have a word-prefix match on "go"; primary boosts
    // Go to Workspace... above Go to agent... within the same tier.
    const filter = makePaletteFilter({
      isPageScoped: () => false,
      isPrimary: (id) => id === "workspaces.switch",
      isAtRoot: true,
    });
    expect(filter(switchValue, "go")).toBeGreaterThan(filter(otherValue, "go"));
  });

  it("primary boost cannot promote across tiers", () => {
    // A subsequence-only primary cannot beat a non-primary substring.
    const filter = makePaletteFilter({
      isPageScoped: () => false,
      isPrimary: () => true,
      isAtRoot: true,
    });
    const primarySubseq = filter(buildItemValue({ title: "Trees and tools", id: "x" }), "tas");
    const nonPrimarySubstring = filter(buildItemValue({ title: "fast and tas", id: "y" }), "tas");
    expect(nonPrimarySubstring).toBeGreaterThan(primarySubseq);
  });

  it("does NOT apply the penalty when not at root", () => {
    const value = buildItemValue({ title: "General", id: "settings.page.general" });
    const filter = makePaletteFilter({
      isPageScoped: () => true,
      isAtRoot: false,
    });
    expect(filter(value, "general")).toBe(paletteFilter(value, "general"));
  });

  it("returns 0 for non-matches without invoking isPageScoped", () => {
    let calls = 0;
    const filter = makePaletteFilter({
      isPageScoped: (): boolean => {
        calls += 1;
        return true;
      },
      isAtRoot: true,
    });
    expect(filter(switchValue, "xyzqq")).toBe(0);
    expect(calls).toBe(0);
  });

  it("getBoost multiplies the score for the boosted command id", () => {
    // Without boost: word-prefix on "actions" → 200, then
    // PAGE_SCOPED_PENALTY (×0.25) → 50.
    // With boost ×8: 50 × 8 = 400.
    const togglePanel = buildItemValue({ title: "Toggle Actions", id: "view.toggle_panel.actions" });
    const settingsRow = buildItemValue({ title: "Actions", id: "settings.page.actions" });
    const filter = makePaletteFilter({
      isPageScoped: () => true,
      getBoost: (id) => (id.startsWith("view.toggle_panel.") ? 8 : undefined),
      isAtRoot: true,
    });
    // The Settings sub-page row gets an EXACT match (1000 → 250 with
    // penalty); the panel toggle gets a boosted word-prefix (50 × 8 =
    // 400). The boost is what makes the panel toggle lead.
    expect(filter(togglePanel, "actions")).toBeGreaterThan(filter(settingsRow, "actions"));
  });

  it("getBoost is ignored when the command id is unboosted (returns undefined)", () => {
    const value = buildItemValue({ title: "Open Settings", id: "settings.open" });
    const boostedFilter = makePaletteFilter({
      isPageScoped: () => false,
      getBoost: () => undefined,
      isAtRoot: true,
    });
    const plainFilter = makePaletteFilter({
      isPageScoped: () => false,
      isAtRoot: true,
    });
    expect(boostedFilter(value, "settings")).toBe(plainFilter(value, "settings"));
  });

  it("getBoost values strictly between 0 and 1 demote the score (used by settings sub-page rows)", () => {
    const value = buildItemValue({ title: "Open Settings", id: "settings.open" });
    const filter = makePaletteFilter({
      isPageScoped: () => false,
      getBoost: () => 0.5,
      isAtRoot: true,
    });
    expect(filter(value, "settings")).toBe(paletteFilter(value, "settings") * 0.5);
  });

  it("getBoost values ≤ 0 are ignored (use `when` to hide rows, not a 0 boost)", () => {
    const value = buildItemValue({ title: "Open Settings", id: "settings.open" });
    const filter = makePaletteFilter({
      isPageScoped: () => false,
      getBoost: () => 0,
      isAtRoot: true,
    });
    expect(filter(value, "settings")).toBe(paletteFilter(value, "settings"));
  });

  it("regression: settings sub-page rows rank below any matching non-settings row", () => {
    // Real bug from the screenshot: typing "file browser" surfaced the
    // Settings: File browser sub-page row above the "Toggle File browser"
    // panel toggle. Settings sub-page rows now carry boost=0.0001 so
    // their max-possible score (1000 × 0.25 × 0.0001 = 0.025) is below
    // the page-scoped subsequence floor (1.0 × 0.25 = 0.25) of any
    // other matching row.
    const settingsFiles = buildItemValue({ title: "File browser", id: "settings.page.files" });
    const togglePanelFiles = buildItemValue({ title: "Toggle File browser", id: "view.toggle_panel.files" });
    const filter = makePaletteFilter({
      isPageScoped: () => true,
      getBoost: (id) => {
        if (id.startsWith("settings.page.")) return 0.0001;
        if (id.startsWith("view.toggle_panel.")) return 8;
        return undefined;
      },
      isAtRoot: true,
    });
    expect(filter(togglePanelFiles, "file browser")).toBeGreaterThan(filter(settingsFiles, "file browser"));
  });

  it("regression: settings sub-page rows still appear when nothing else matches", () => {
    // The strong demote (×0.0001) must not zero out the score — when a
    // sub-page row is the only match, it should still surface.
    const settingsGeneral = buildItemValue({ title: "General", id: "settings.page.general" });
    const filter = makePaletteFilter({
      isPageScoped: () => true,
      getBoost: (id) => (id.startsWith("settings.page.") ? 0.0001 : undefined),
      isAtRoot: true,
    });
    expect(filter(settingsGeneral, "general")).toBeGreaterThan(0);
  });

  it("regression: typing a panel display name surfaces the panel toggle above Settings: <same name>", () => {
    // Coworker feedback: typing "Actions" used to land on the Settings
    // sub-page row before the View panel toggle. The boost applied to
    // dynamic panel toggles fixes that.
    const togglePanelActions = buildItemValue({ title: "Toggle Actions", id: "view.toggle_panel.actions" });
    const settingsActions = buildItemValue({ title: "Actions", id: "settings.page.actions" });
    const filter = makePaletteFilter({
      isPageScoped: () => true,
      getBoost: (id) => (id.startsWith("view.toggle_panel.") ? 8 : undefined),
      isAtRoot: true,
    });
    expect(filter(togglePanelActions, "Actions")).toBeGreaterThan(filter(settingsActions, "Actions"));
  });

  it('"browser" search matches the file-browser panel toggle via its display name', () => {
    // The panel's display name was renamed from "Files" to "File browser"
    // so searches like "browser" or "file browser" hit the title (not a
    // capped keyword), and the boosted toggle row surfaces alongside the
    // Settings entry.
    const togglePanelFiles = buildItemValue({ title: "Toggle File browser", id: "view.toggle_panel.files" });
    const filter = makePaletteFilter({
      isPageScoped: () => true,
      getBoost: (id) => (id.startsWith("view.toggle_panel.") ? 8 : undefined),
      isAtRoot: true,
    });
    expect(filter(togglePanelFiles, "browser", ["panel", "files", "explorer"])).toBeGreaterThan(0);
    expect(filter(togglePanelFiles, "file browser", ["panel", "files", "explorer"])).toBeGreaterThan(0);
  });
});
