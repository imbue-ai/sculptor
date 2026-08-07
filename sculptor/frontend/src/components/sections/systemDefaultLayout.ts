// System Layouts: the built-in, read-only arrangements that always appear in the
// switcher — "System Default" plus a set of task presets (Chat, Review, Terminal,
// Browser). None are stored in savedLayouts; they are synthesized here so they can
// never drift and can never be deleted, renamed, or edited. Applying one arranges
// the tool panels + geometry ADDITIVELY and leaves the workspace's agents/terminals
// in place — a preset that "focuses" a section just collapses the others, so nothing
// is ever closed.
//
// A `defaultLayoutId` that is unset or points at a since-deleted layout resolves
// back to System Default (see savedLayoutAtoms), so there is always a valid default.

import { captureLayout } from "./layoutCapture.ts";
import { buildDefaultWorkspaceLayout } from "./persistence/defaultLayout.ts";
import type { CapturedLayout, SavedLayout } from "./persistence/types.ts";
import { DEFAULT_SECTION_SIZES, SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import { makeAgentPanelId, makeTerminalPanelId } from "./registry/dynamicPanels.tsx";

export const SYSTEM_DEFAULT_LAYOUT_ID = "system-default";
const SYSTEM_DEFAULT_LAYOUT_NAME = "System Default";

// The switcher summary shown for System Default. Fixed (rather than derived from the
// captured statics) so it can name the dynamic terminal the seeding places, which a
// static-only capture can't — matching the mock's "Terminal below".
export const SYSTEM_DEFAULT_LAYOUT_SUMMARY = "Files, Changes & Commits · Terminal below";

function buildSystemDefaultLayout(): SavedLayout {
  // Placeholder ids only exist so buildDefaultWorkspaceLayout can place its center
  // agent + bottom terminal; captureLayout then strips them (they are dynamic), so
  // the captured shape is Files/Changes/Commits in an expanded left, right + bottom
  // collapsed, center active, default sizes — the static skeleton of the default.
  const base = buildDefaultWorkspaceLayout({
    agentPanelId: makeAgentPanelId("system-default-placeholder"),
    terminalPanelId: makeTerminalPanelId("system-default-placeholder", 1),
  });
  return {
    id: SYSTEM_DEFAULT_LAYOUT_ID,
    name: SYSTEM_DEFAULT_LAYOUT_NAME,
    captured: captureLayout(base, null),
    version: SAVED_LAYOUT_VERSION,
    // Switching to the default tidies, so it resets to the clean default arrangement
    // (closes panels you opened on top) rather than layering on additively.
    tidyOnApply: true,
  };
}

// Deterministic and side-effect-free, so it is safe to build once at module load.
export const SYSTEM_DEFAULT_LAYOUT: SavedLayout = buildSystemDefaultLayout();

// --- Task presets ----------------------------------------------------------

export const SYSTEM_CHAT_LAYOUT_ID = "system-chat";
export const SYSTEM_REVIEW_LAYOUT_ID = "system-review";
export const SYSTEM_TERMINAL_LAYOUT_ID = "system-terminal";
export const SYSTEM_BROWSER_LAYOUT_ID = "system-browser";

// The starting point for every preset: center only. center is always expanded (never
// listed in `expanded`); every other section collapsed, no static panels, default
// sizes. A preset then opens/expands just the sections it focuses. Collapsing a
// section hides it without closing anything (apply is additive).
const CENTER_ONLY: CapturedLayout = {
  placement: {},
  order: {},
  activePanel: {},
  expanded: { left: false, right: false, bottom: false },
  splits: {},
  sectionSizes: DEFAULT_SECTION_SIZES,
  maximizedSection: null,
  activeSubSection: "center",
};

// Every preset tidies on apply: switching to one closes the static panels it doesn't
// declare (never agents/terminals), so it produces the clean arrangement it describes
// rather than layering on top of whatever was already open.
function presetLayout(id: string, name: string, captured: Partial<CapturedLayout>): SavedLayout {
  return { id, name, version: SAVED_LAYOUT_VERSION, tidyOnApply: true, captured: { ...CENTER_ONLY, ...captured } };
}

// Chat: just the center agent — every other section collapsed. Nothing is closed;
// the side panels are only hidden.
const CHAT_LAYOUT = presetLayout(SYSTEM_CHAT_LAYOUT_ID, "Chat", {});

// Review: Review All front-and-center, maximized to fill the workspace.
const REVIEW_LAYOUT = presetLayout(SYSTEM_REVIEW_LAYOUT_ID, "Review", {
  placement: { "review-all": "center" },
  order: { center: ["review-all"] },
  activePanel: { center: "review-all" },
  maximizedSection: "center",
});

// Terminal: the bottom section open at about half height, chat above it.
const TERMINAL_LAYOUT = presetLayout(SYSTEM_TERMINAL_LAYOUT_ID, "Terminal", {
  expanded: { left: false, right: false, bottom: true },
  sectionSizes: { left: 20, right: 20, bottom: 50 },
  activeSubSection: "bottom",
});

// Browser: the Browser panel in the right section at about half width, chat beside it.
const BROWSER_LAYOUT = presetLayout(SYSTEM_BROWSER_LAYOUT_ID, "Browser", {
  placement: { browser: "right" },
  order: { right: ["browser"] },
  activePanel: { right: "browser" },
  expanded: { left: false, right: true, bottom: false },
  sectionSizes: { left: 20, right: 50, bottom: 30 },
  activeSubSection: "right",
});

// The task presets, in switcher display order (after System Default).
export const SYSTEM_PRESET_LAYOUTS: ReadonlyArray<SavedLayout> = [
  CHAT_LAYOUT,
  REVIEW_LAYOUT,
  TERMINAL_LAYOUT,
  BROWSER_LAYOUT,
];

// Every built-in, System Default first. resolvedLayoutsAtom prepends these to the
// user's saved layouts.
export const SYSTEM_LAYOUTS: ReadonlyArray<SavedLayout> = [SYSTEM_DEFAULT_LAYOUT, ...SYSTEM_PRESET_LAYOUTS];

// Fixed one-line summaries (the switcher's muted row subtitle). Presets carry little
// or no static content, so a derived summary would read empty — these state intent.
export const SYSTEM_LAYOUT_SUMMARIES: Readonly<Record<string, string>> = {
  [SYSTEM_DEFAULT_LAYOUT_ID]: SYSTEM_DEFAULT_LAYOUT_SUMMARY,
  [SYSTEM_CHAT_LAYOUT_ID]: "Just the chat",
  [SYSTEM_REVIEW_LAYOUT_ID]: "Review All, maximized",
  [SYSTEM_TERMINAL_LAYOUT_ID]: "Terminal below, half height",
  [SYSTEM_BROWSER_LAYOUT_ID]: "Browser on the right, half width",
};

const SYSTEM_LAYOUT_IDS: ReadonlySet<string> = new Set(SYSTEM_LAYOUTS.map((layout) => layout.id));

export function isSystemDefaultLayoutId(id: string): boolean {
  return id === SYSTEM_DEFAULT_LAYOUT_ID;
}

// True for any built-in (System Default or a preset) — the read-only set that can't
// be edited, renamed, or deleted.
export function isSystemLayoutId(id: string): boolean {
  return SYSTEM_LAYOUT_IDS.has(id);
}
