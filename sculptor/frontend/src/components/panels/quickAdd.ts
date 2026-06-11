import type { PanelDefinition } from "~/components/panels/types.ts";

/**
 * The empty-section "Quick add" shortcuts: the create actions (new agent /
 * new terminal) followed by every static panel not currently open anywhere,
 * in a fixed priority order. Callers pass the unplaced static panels (see
 * `useUnplacedStaticPanels`) — open panels never appear here.
 */
export type QuickAddItem =
  | { kind: "create-terminal" }
  | { kind: "create-agent" }
  | { kind: "panel"; panel: PanelDefinition };

const CREATE_AGENT = "__agent__";
const CREATE_TERMINAL = "__terminal__";

const QUICK_ADD_ORDER: ReadonlyArray<string> = [
  CREATE_AGENT,
  CREATE_TERMINAL,
  "files",
  "changes",
  "commits",
  "browser",
  "review-all",
  "skills",
  "notes",
  "actions",
];

export const pickQuickAdd = (unplacedStaticPanels: ReadonlyArray<PanelDefinition>): ReadonlyArray<QuickAddItem> => {
  const byId = new Map(unplacedStaticPanels.map((panel) => [panel.id, panel]));
  const ordered = QUICK_ADD_ORDER.flatMap((id): ReadonlyArray<QuickAddItem> => {
    if (id === CREATE_AGENT) return [{ kind: "create-agent" }];
    if (id === CREATE_TERMINAL) return [{ kind: "create-terminal" }];
    const panel = byId.get(id);
    return panel ? [{ kind: "panel", panel }] : [];
  });
  // Panels the fixed order doesn't know about (new/experimental) go last
  // rather than silently disappearing.
  const known = new Set(QUICK_ADD_ORDER);
  const rest = unplacedStaticPanels.filter((panel) => !known.has(panel.id));
  return [...ordered, ...rest.map((panel): QuickAddItem => ({ kind: "panel", panel }))];
};
