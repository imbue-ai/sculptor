// The panel registry: the join point between layout state (which references panels
// by id) and content (which renders them). Static single-instance panels carry
// metadata here; their actual components are supplied through registerPanelComponent
// (called once from registerPanels at app load) so this module never imports the
// component modules directly. Dynamic agent/terminal panels are derived in dynamicPanels.
// Panels carry no enable/disable flags; a panel's visibility is purely its placement
// in the layout.

import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";
import type { LucideIcon } from "lucide-react";
import { FileText, GitBranch, GitCommitVertical, Globe, ListChecks, NotebookPen, Sparkles, Zap } from "lucide-react";
import type { ComponentType } from "react";

import { tasksArrayAtom } from "../../../common/state/atoms/tasks.ts";
import type { AgentDotStatus } from "../../statusDot/statusUtils.ts";
import { activePanelIdInSubSectionAtom, panelsInSubSectionAtom } from "../sectionAtoms.ts";
import type { PanelId, SubSectionId } from "../sectionTypes.ts";

export type PanelKind = "static" | "agent" | "terminal";

// A single invocable row in a panel tab's context menu. `icon` renders leading;
// `destructive` styles it as a danger action (red); `separatorBefore` opens a new
// visual group above it (suppressed for the menu's first row). `testId` is required:
// every actionable row is addressed by its stable TAB_CONTEXT_MENU_* id in tests and
// keyed by it in the renderer, so a row without one would be untestable and unkeyed.
export type PanelContextMenuAction = {
  kind: "action";
  label: string;
  action: () => void;
  testId: string;
  icon?: LucideIcon;
  disabled?: boolean;
  destructive?: boolean;
  separatorBefore?: boolean;
};

// A labeled submenu grouping related actions behind a single trigger (e.g. the agent's
// Diagnostics copy items), so they don't crowd the top level. One level deep only.
// `testId` is required for the same reason as PanelContextMenuAction — the trigger is
// located by it in tests and used as the row's React key.
export type PanelContextMenuSubmenu = {
  kind: "submenu";
  label: string;
  items: ReadonlyArray<PanelContextMenuAction>;
  testId: string;
  icon?: LucideIcon;
  separatorBefore?: boolean;
};

export type PanelContextMenuItem = PanelContextMenuAction | PanelContextMenuSubmenu;

export type PanelDefinition = {
  id: PanelId;
  displayName: string;
  icon: LucideIcon;
  kind: PanelKind;
  // Optional: review-all and browser have no default section (not opened by default).
  defaultSection?: SubSectionId;
  // Secondary text shown under the panel's label in the add-panel dropdown. Only
  // extension panels supply it; static built-ins leave it unset and render title-only.
  description?: string;
  component: ComponentType;
  // The agent/terminal-agent status reflected by the tab's status dot. Exposed on the
  // tab element as `data-dot-status` so tests can read read/unread/running/waiting/error
  // without depending on the dot's visual styling. Unset for static/plain-terminal panels.
  dotStatus?: AgentDotStatus;
  contextMenuActions?: ReadonlyArray<PanelContextMenuItem>;
  // When set, the tab's close button runs this instead of removing the panel from the
  // layout. Multi-instance panels use it so closing an agent/terminal tab deletes the
  // underlying agent/terminal (with its confirmation dialog) rather than just hiding it
  // Static panels leave it unset and fall back to closePanelAtom.
  onRequestClose?: () => void;
  // When set, committing an inline tab rename runs this with the new name to persist it
  // on the underlying entity (agent title / terminal tab label). Only multi-instance
  // panels supply it; static panels leave it unset since they cannot be renamed.
  // Mirrors onRequestClose.
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

// Component registration indirection: registerPanels supplies each static panel's
// component via registerPanelComponent at app load; the registry composes metadata +
// the registered component. A panel with no registered component yet renders nothing.
const registeredComponents = new Map<PanelId, ComponentType>();

const MissingPanelPlaceholder: ComponentType = () => null;

export function registerPanelComponent(id: PanelId, component: ComponentType): void {
  registeredComponents.set(id, component);
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

// The minimal extension-panel shape this registry adapts. Declared structurally (rather
// than importing the extensions module) so the registry stays extension-agnostic and the
// dependency only points one way (extensions → sections, never the reverse).
export type ExtensionRegistryPanel = {
  id: PanelId;
  displayName: string;
  icon: LucideIcon;
  component: ComponentType;
  defaultSection?: SubSectionId;
  description?: string;
};

// Adapt extension-contributed panels into registry PanelDefinitions so the new shell can
// resolve and render them. Extension panels are single-instance ("static") and
// host-managed; the extension's component is already wrapped (error boundary + contexts)
// by the loader before it reaches here.
export function buildExtensionPanelDefinitions(
  extensionPanels: ReadonlyArray<ExtensionRegistryPanel>,
): ReadonlyArray<PanelDefinition> {
  return extensionPanels.map((panel) => ({
    id: panel.id,
    displayName: panel.displayName,
    icon: panel.icon,
    kind: "static",
    defaultSection: panel.defaultSection,
    description: panel.description,
    component: panel.component,
  }));
}

// The current registry (static + extension + dynamic). Kept in sync with the active
// workspace's agent/terminal panels and the loaded extensions by useWorkspaceDynamicPanels;
// defaults to the static panels so reads before sync never crash.
export const panelRegistryAtom = atom<ReadonlyArray<PanelDefinition>>(buildStaticPanelDefinitions());

// True when two panel definitions are equal for render purposes: same identity, or
// all of the stable, render-relevant fields match. A registry rebuild on a task tick
// produces fresh PanelDefinition objects even when nothing a tab cares about changed,
// so without this comparator selectAtom would re-emit (new object reference) and
// re-render the tab every tick. `component` and `icon` are identity-stable
// (registeredComponents map / dynamicPanels componentCache; icons are module
// constants) and `dotStatus` is a scalar, so comparing these fields suppresses
// spurious re-emits while still re-rendering on a real change (e.g. rename or a
// dot-status change).
//
// The callback fields (contextMenuActions / onRequestClose / onRename) are deliberately
// omitted: every registry derivation rebuilds them as fresh closures, so comparing them
// by reference would defeat the comparator. Omitting them is safe because SectionHeader
// never invokes a callback captured through this guarded slice — it re-reads the CURRENT
// definition from panelRegistryAtom at menu-open / invocation time, so a suppressed
// re-emit cannot strand a stale callback.
function panelDefinitionEqual(a: PanelDefinition | undefined, b: PanelDefinition | undefined): boolean {
  return (
    a === b ||
    (a !== undefined &&
      b !== undefined &&
      a.id === b.id &&
      a.displayName === b.displayName &&
      a.icon === b.icon &&
      a.kind === b.kind &&
      a.defaultSection === b.defaultSection &&
      a.description === b.description &&
      a.dotStatus === b.dotStatus &&
      a.component === b.component)
  );
}

// True when two registries hold pairwise render-equal definitions in the same order.
// The registry sync hook uses this to skip the atom write for rebuilds that changed
// nothing (task ticks), so whole-registry subscribers don't re-render several times per
// second during streaming. Because panelDefinitionEqual ignores the callback fields,
// the hook must separately force a write when a callback INPUT (agent diagnostics)
// changes — see useWorkspaceDynamicPanels.
export function panelRegistriesEqual(a: ReadonlyArray<PanelDefinition>, b: ReadonlyArray<PanelDefinition>): boolean {
  return a.length === b.length && a.every((definition, index) => panelDefinitionEqual(definition, b[index]));
}

// A single panel's definition, sliced out of the registry and memoized per id.
// Tabs subscribe to this rather than the whole registry so a registry rebuild on a
// task tick (which produces a new array but the same per-id definition) does not
// re-render every tab — only the tab whose own definition changed.
//
// The family is keyed by panel id, which for agents/terminals is unbounded across a
// session, so the dynamic-panel eviction (deriveDynamicPanels) removes an entry once
// its task/terminal is gone — alongside its cached component.
export const panelDefinitionByIdAtom = atomFamily((panelId: PanelId) =>
  selectAtom(
    panelRegistryAtom,
    (registry): PanelDefinition | undefined => registry.find((definition) => definition.id === panelId),
    panelDefinitionEqual,
  ),
);

// The registry-aware resolution of a sub-section's active panel id — the id both
// SectionBody renders and SectionHeader highlights, so the highlighted tab always
// matches the rendered body.
//
// The persisted layout can name a panel id with no current registry definition:
// extension registration is async, so on every reload a persisted extension-panel id is
// transiently unregistered, and unloading an extension removes its definitions while its
// panels stay in the layout. Resolution therefore falls back — at read time only —
// to the first OPEN panel in the sub-section that still has a definition (undefined
// when none does, rendering the empty state). The layout itself must NEVER be
// written/pruned in response: because the stored active id is left intact, the
// resolution self-heals back to it the moment its definition (re)registers.
export const resolvedActivePanelIdInSubSectionAtom = atomFamily((subSection: SubSectionId) =>
  atom((get): PanelId | undefined => {
    const registry = get(panelRegistryAtom);
    const isRegistered = (panelId: PanelId): boolean => registry.some((definition) => definition.id === panelId);
    const activePanelId = get(activePanelIdInSubSectionAtom(subSection));
    if (activePanelId !== undefined && isRegistered(activePanelId)) {
      return activePanelId;
    }
    return get(panelsInSubSectionAtom(subSection)).find(isRegistered);
  }),
);

// The layout↔registry join SectionBody subscribes to: the resolved component for the
// sub-section's active panel. Returns a stable reference per panel id (static
// component or identity-cached dynamic component), so a registry rebuild on a task
// tick never remounts live panel content.
export const activePanelComponentInSubSectionAtom = atomFamily((subSection: SubSectionId) =>
  atom((get): ComponentType | undefined => {
    const activePanelId = get(resolvedActivePanelIdInSubSectionAtom(subSection));
    if (activePanelId === undefined) {
      return undefined;
    }
    return get(panelRegistryAtom).find((definition) => definition.id === activePanelId)?.component;
  }),
);

// True while a sub-section has a placed panel that currently resolves to NO
// component ONLY because the agent/task snapshot hasn't arrived yet. Agent panels
// are registered off `tasksArrayAtom` (via useWorkspaceDynamicPanels), which is
// `undefined` until the first task frame — so on a reload the layout still names
// an `agent:<taskId>` panel the registry can't resolve, and the sub-section would
// otherwise fall through to the "Add panel" empty state as if the workspace were
// empty. SectionBody reads this to show a loading placeholder for that window
// instead; the resolved-component undefined check alone can't tell "agent panel
// still loading" from "genuinely empty section".
//
// It flips false the moment the task snapshot arrives: the placed panel then either
// registers (a component resolves, so this is already false) or its task is gone
// (the section is genuinely empty and correctly shows the empty state). Guarding on
// a non-empty placement keeps a truly empty sub-section showing its launcher even
// during the load window.
export const isSubSectionPanelLoadingAtom = atomFamily((subSection: SubSectionId) =>
  atom((get): boolean => {
    if (get(activePanelComponentInSubSectionAtom(subSection)) !== undefined) {
      return false;
    }

    if (get(tasksArrayAtom) !== undefined) {
      return false;
    }
    return get(panelsInSubSectionAtom(subSection)).length > 0;
  }),
);
