// The panel registry: the join point between layout state (which references panels
// by id) and content (which renders them). Static single-instance panels carry
// metadata here; their actual components are supplied through registerPanelComponent
// at import time (Phase 2/3) so this Phase-1 module never forward-imports components
// that do not exist yet. Dynamic agent/terminal panels are derived in dynamicPanels.
// There is NO enabled/defaultEnabled/isBuiltin flag — the Panels settings page is
// gone.

import type { Atom } from "jotai";
import { atom } from "jotai";
import { selectAtom } from "jotai/utils";
import type { LucideIcon } from "lucide-react";
import { FileText, GitBranch, GitCommitVertical, Globe, ListChecks, NotebookPen, Sparkles, Zap } from "lucide-react";
import type { ComponentType, ReactNode } from "react";

import type { AgentDotStatus } from "../../statusDot/statusUtils.ts";
import { activePanelIdInSubSectionAtom } from "../sectionAtoms.ts";
import type { PanelId, SubSectionId } from "../sectionTypes.ts";

export type PanelKind = "static" | "agent" | "terminal";

export type PanelContextMenuItem = { label: string; action: () => void; disabled?: boolean };

export type PanelDefinition = {
  id: PanelId;
  displayName: string;
  icon: LucideIcon;
  kind: PanelKind;
  // Optional: review-all and browser have no default section (not opened by default).
  defaultSection?: SubSectionId;
  component: ComponentType;
  tabIcon?: ReactNode;
  // The agent/terminal-agent status reflected by the tab's status dot. Exposed on the
  // tab element as `data-dot-status` so tests can read read/unread/running/waiting/error
  // without depending on the dot's visual styling. Unset for static/plain-terminal panels.
  dotStatus?: AgentDotStatus;
  contextMenuActions?: ReadonlyArray<PanelContextMenuItem>;
  // When set, the tab's close button runs this instead of removing the panel from the
  // layout. Multi-instance panels use it so closing an agent/terminal tab deletes the
  // underlying agent/terminal (with its confirmation dialog) rather than just hiding it
  // (AGENT-04/08). Static panels leave it unset and fall back to closePanelAtom.
  onRequestClose?: () => void;
  // When set, committing an inline tab rename runs this with the new name to persist it
  // on the underlying entity (agent title / terminal tab label). Only multi-instance
  // panels supply it; static panels leave it unset since they cannot be renamed
  // (PANEL-11). Mirrors onRequestClose.
  onRename?: (newName: string) => void;
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

// The minimal plugin-panel shape this registry adapts. Declared structurally (rather
// than importing the plugins module) so the registry stays plugin-agnostic and the
// dependency only points one way (plugins → sections, never the reverse).
export type PluginRegistryPanel = {
  id: PanelId;
  displayName: string;
  icon: LucideIcon;
  component: ComponentType;
  defaultSection?: SubSectionId;
};

// Adapt plugin-contributed panels into registry PanelDefinitions so the new shell can
// resolve and render them. Plugin panels are single-instance ("static") and
// host-managed; the plugin's component is already wrapped (error boundary + contexts)
// by the loader before it reaches here.
export function buildPluginPanelDefinitions(
  pluginPanels: ReadonlyArray<PluginRegistryPanel>,
): ReadonlyArray<PanelDefinition> {
  return pluginPanels.map((panel) => ({
    id: panel.id,
    displayName: panel.displayName,
    icon: panel.icon,
    kind: "static",
    defaultSection: panel.defaultSection,
    component: panel.component,
  }));
}

// The current registry (static + plugin + dynamic). Kept in sync with the active
// workspace's agent/terminal panels and the loaded plugins by useWorkspaceDynamicPanels;
// defaults to the static panels so reads before sync never crash.
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

// A single panel's definition, sliced out of the registry and memoized per id.
// Tabs subscribe to this rather than the whole registry so a registry rebuild on a
// task tick (which produces a new array but the same per-id definition) does not
// re-render every tab — only the tab whose own definition changed.
export const panelDefinitionByIdAtom = memoizedAtomByKey<PanelId, PanelDefinition | undefined>((panelId) =>
  selectAtom(panelRegistryAtom, (registry) => registry.find((definition) => definition.id === panelId)),
);

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
