// The undeletable "System Default" Layout. It is NOT stored in savedLayouts; it is
// synthesized here from buildDefaultWorkspaceLayout so it can never drift from what
// a first-visit workspace seeds. Its captured portion is static-only (the seeded
// agent/terminal are stripped by captureLayout), so applying it arranges the tool
// panels + geometry and leaves the workspace's agents/terminals in place.
//
// A `defaultLayoutId` that is unset or points at a since-deleted layout resolves
// back to this (see savedLayoutAtoms), so there is always a valid default.

import { captureLayout } from "./layoutCapture.ts";
import { buildDefaultWorkspaceLayout } from "./persistence/defaultLayout.ts";
import type { SavedLayout } from "./persistence/types.ts";
import { SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
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
  };
}

// Deterministic and side-effect-free, so it is safe to build once at module load.
export const SYSTEM_DEFAULT_LAYOUT: SavedLayout = buildSystemDefaultLayout();

export function isSystemDefaultLayoutId(id: string): boolean {
  return id === SYSTEM_DEFAULT_LAYOUT_ID;
}
