// The panel registry: the join point between layout state (which references panels
// by id) and content (which renders them). Static single-instance panels carry
// metadata here; their actual components are supplied through registerPanelComponent
// at import time (Phase 2/3) so this Phase-1 module never forward-imports components
// that do not exist yet. Dynamic agent/terminal panels are derived in dynamicPanels.
// There is NO enabled/defaultEnabled/isBuiltin flag — the Panels settings page is
// gone.

import type { Atom } from "jotai";
import { atom } from "jotai";
import type { LucideIcon } from "lucide-react";
import { FileText, GitBranch, GitCommitVertical, Globe, ListChecks, NotebookPen, Sparkles, Zap } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

import { activePanelIdInSubSectionAtom } from "../sectionAtoms.ts";
import type { PanelId, SubSectionId } from "../sectionTypes.ts";

export type PanelKind = "static" | "agent" | "terminal";

export type PanelContextMenuItem = { label: string; action: () => void };

export type PanelDefinition = {
  id: PanelId;
  displayName: string;
  icon: LucideIcon;
  kind: PanelKind;
  // Optional: review-all and browser have no default section (not opened by default).
  defaultSection?: SubSectionId;
  component: ComponentType;
  tabIcon?: ReactNode;
  contextMenuActions?: ReadonlyArray<PanelContextMenuItem>;
};

// Agent and terminal are the only multi-instance (renamable) panels.
export function isMultiInstanceKind(kind: PanelKind): boolean {
  return kind === "agent" || kind === "terminal";
}

// Icons reference lucide-react. lucide names: agent → Bot, terminal → Terminal.
type StaticPanelMeta = { id: PanelId; displayName: string; icon: LucideIcon; defaultSection?: SubSectionId };

export const STATIC_PANEL_METADATA: ReadonlyArray<StaticPanelMeta> = [
  { id: "files", displayName: "Files", icon: FileText, defaultSection: "left" },
  { id: "changes", displayName: "Changes", icon: GitBranch, defaultSection: "left" },
  { id: "commits", displayName: "Commits", icon: GitCommitVertical, defaultSection: "left" },
  { id: "review-all", displayName: "Review All", icon: ListChecks },
  { id: "actions", displayName: "Actions", icon: Zap, defaultSection: "right" },
  { id: "skills", displayName: "Skills", icon: Sparkles, defaultSection: "right" },
  { id: "browser", displayName: "Browser", icon: Globe },
  { id: "notes", displayName: "Notes", icon: NotebookPen, defaultSection: "right" },
];

// Component registration indirection: the static panel modules register their
// component at import time; the registry composes metadata + the registered
// component. A panel with no registered component yet renders nothing.
const registeredComponents = new Map<PanelId, ComponentType>();

const MissingPanelPlaceholder: ComponentType = () => null;

export function registerPanelComponent(id: PanelId, component: ComponentType): void {
  registeredComponents.set(id, component);
}

export function getRegisteredPanelComponent(id: PanelId): ComponentType | undefined {
  return registeredComponents.get(id);
}

export function buildStaticPanelDefinitions(): ReadonlyArray<PanelDefinition> {
  return STATIC_PANEL_METADATA.map((meta) => ({
    id: meta.id,
    displayName: meta.displayName,
    icon: meta.icon,
    kind: "static",
    defaultSection: meta.defaultSection,
    component: registeredComponents.get(meta.id) ?? MissingPanelPlaceholder,
  }));
}

// The current registry (static + dynamic). Kept in sync with the active workspace's
// agent/terminal panels by useSyncPanelRegistry (Task 6.2); defaults to the static
// panels so reads before sync never crash.
export const panelRegistryAtom = atom<ReadonlyArray<PanelDefinition>>(buildStaticPanelDefinitions());

function memoizedAtomByKey<TKey extends string, TValue>(
  factory: (key: TKey) => Atom<TValue>,
): (key: TKey) => Atom<TValue> {
  const cache = new Map<string, Atom<TValue>>();
  return (key) => {
    let cached = cache.get(key);
    if (cached === undefined) {
      cached = factory(key);
      cache.set(key, cached);
    }
    return cached;
  };
}

// The layout↔registry join SectionBody subscribes to: the resolved component for the
// sub-section's active panel. Returns a stable reference per panel id (static
// component or identity-cached dynamic component), so a registry rebuild on a task
// tick never remounts live panel content (SWITCH-02).
export const activePanelComponentInSubSectionAtom = memoizedAtomByKey<SubSectionId, ComponentType | undefined>(
  (subSection) =>
    atom((get) => {
      const activePanelId = get(activePanelIdInSubSectionAtom(subSection));
      if (activePanelId === undefined) {
        return undefined;
      }
      return get(panelRegistryAtom).find((definition) => definition.id === activePanelId)?.component;
    }),
);
