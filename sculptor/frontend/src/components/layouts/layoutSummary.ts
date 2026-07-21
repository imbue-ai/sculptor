// Derive the muted one-line summary the switcher shows under a layout's name, e.g.
// "Changes & Commits left · Browser right". Built from a layout's captured STATIC
// panels grouped by section (agents/terminals aren't captured, so they never
// appear). Pure — the caller supplies a panel-id → display-name resolver from the
// live registry.

import type { CapturedLayout } from "~/components/sections/persistence/types.ts";
import type { PanelId, SectionId } from "~/components/sections/sectionTypes.ts";
import { SECTION_IDS, toSecondary, toSection } from "~/components/sections/sectionTypes.ts";

// "below" reads better than "bottom" for the bottom section; the rest are literal.
const SECTION_WORD: Readonly<Record<SectionId, string>> = {
  left: "left",
  center: "center",
  right: "right",
  bottom: "below",
};

function joinNames(names: ReadonlyArray<string>): string {
  if (names.length <= 1) {
    return names.join("");
  }

  if (names.length === 2) {
    return `${names[0]} & ${names[1]}`;
  }
  return `${names.slice(0, -1).join(", ")} & ${names[names.length - 1]}`;
}

// The declared static panels placed in a section (primary then secondary), in
// captured tab order, with any placed-but-unordered ids appended.
function staticPanelsInSection(captured: CapturedLayout, section: SectionId): Array<PanelId> {
  const ids: Array<PanelId> = [];
  for (const subSection of [section, toSecondary(section)]) {
    for (const id of captured.order[subSection] ?? []) {
      if (captured.placement[id] === subSection && !ids.includes(id)) {
        ids.push(id);
      }
    }
  }

  for (const id of Object.keys(captured.placement) as Array<PanelId>) {
    const subSection = captured.placement[id];
    if (subSection !== undefined && toSection(subSection) === section && !ids.includes(id)) {
      ids.push(id);
    }
  }
  return ids;
}

export function describeLayout(captured: CapturedLayout, getPanelName: (id: PanelId) => string): string {
  const parts: Array<string> = [];
  for (const section of SECTION_IDS) {
    const names = staticPanelsInSection(captured, section).map(getPanelName);
    if (names.length > 0) {
      parts.push(`${joinNames(names)} ${SECTION_WORD[section]}`);
    }
  }
  // No tool panels means the layout is just the agent's space.
  return parts.length === 0 ? "Just the agent, full width" : parts.join(" · ");
}
